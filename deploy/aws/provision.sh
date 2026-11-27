#!/usr/bin/env bash
# 과제 확인용 데모를 AWS 서울 리전에 올린다. 여러 번 실행해도 이미 있는 자원은 그대로 쓴다.
#
#   사용자 ──HTTPS──> CloudFront ──HTTP(CloudFront IP만 허용)──> EC2 t4g.small (Docker: gunicorn)
#                                                                  ├──> RDS PostgreSQL 17 (사설, EC2에서만 접근)
#                                                                  ├──> SSM Parameter Store (비밀값)
#                                                                  └──> systemd 타이머 08:00 KST → run_daily_jobs
#
# 운영 목표 구성(ECS Fargate·ALB·EventBridge·SES)은 docs/DEPLOY_AWS.md. 이 스크립트는 그 작은 판이다.
# 필요: AWS CLI v2 로그인(aws login 또는 aws configure), bash, python
#   bash deploy/aws/provision.sh            # 만들기 + 배포
#   bash deploy/aws/provision.sh deploy     # 코드만 다시 배포 (git push 뒤)
set -euo pipefail
export MSYS_NO_PATHCONV=1 AWS_PAGER=""   # Git Bash가 /edu-apply/… 를 파일 경로로 바꾸지 않게
export AWS_REGION=${AWS_REGION:-ap-northeast-2}
APP=edu-apply
HERE=$(cd "$(dirname "$0")" && pwd)
cd "$HERE"
mkdir -p .build
say() { printf '\n== %s\n' "$*"; }
txt() { aws "$@" --output text | tr -d '\r'; }

gen_secret() { python -c "import secrets; print(secrets.token_urlsafe(${1:-32}))" | tr -d '\r'; }
put_param() {  # 이름 값 [overwrite] — 값은 화면에 찍지 않는다
  if [ "${3:-}" = overwrite ] || ! aws ssm get-parameter --name "/$APP/$1" >/dev/null 2>&1; then
    aws ssm put-parameter --name "/$APP/$1" --type SecureString --value "$2" --overwrite >/dev/null
  fi
}

wait_command() {  # command-id instance-id → 최종 상태
  local st=Pending
  while [ "$st" = Pending ] || [ "$st" = InProgress ] || [ "$st" = Delayed ]; do
    sleep 4
    st=$(txt ssm get-command-invocation --command-id "$1" --instance-id "$2" --query Status 2>/dev/null || echo Pending)
  done
  echo "$st"
}

run_deploy() {
  local iid=$1 cmd st
  say "서버에 배포 (SSM Run Command, SSH 키 없음)"
  for _ in $(seq 1 60); do
    [ "$(txt ssm describe-instance-information --filters Key=InstanceIds,Values="$iid" --query 'length(InstanceInformationList)')" = 1 ] && break
    sleep 5
  done
  for _ in $(seq 1 40); do  # 첫 부팅(user_data: 도커·git 설치, 저장소 받기)이 끝날 때까지
    cmd=$(txt ssm send-command --instance-ids "$iid" --document-name AWS-RunShellScript \
      --parameters '{"commands":["test -f /opt/edu-apply/deploy/aws/server_deploy.sh && systemctl is-active docker"]}' \
      --query Command.CommandId)
    [ "$(wait_command "$cmd" "$iid")" = Success ] && break
    sleep 10
  done
  cmd=$(txt ssm send-command --instance-ids "$iid" --document-name AWS-RunShellScript --timeout-seconds 900 \
    --parameters '{"commands":["bash /opt/edu-apply/deploy/aws/server_deploy.sh"],"executionTimeout":["900"]}' \
    --query Command.CommandId)
  st=$(wait_command "$cmd" "$iid")
  txt ssm get-command-invocation --command-id "$cmd" --instance-id "$iid" --query StandardOutputContent | tail -5
  if [ "$st" != Success ]; then
    echo "배포 실패 ($st)" >&2
    txt ssm get-command-invocation --command-id "$cmd" --instance-id "$iid" --query StandardErrorContent | tail -40 >&2
    exit 1
  fi
}

instance_id() {
  txt ec2 describe-instances --filters Name=tag:app,Values=$APP Name=instance-state-name,Values=pending,running,stopping,stopped \
    --query 'Reservations[0].Instances[0].InstanceId'
}

if [ "${1:-}" = deploy ]; then run_deploy "$(instance_id)"; exit 0; fi

ACCOUNT=$(txt sts get-caller-identity --query Account)
say "계정 $ACCOUNT, 리전 $AWS_REGION"

say "네트워크 (기본 VPC)"
VPC=$(txt ec2 describe-vpcs --filters Name=is-default,Values=true --query 'Vpcs[0].VpcId')
[ "$VPC" = None ] && VPC=$(txt ec2 create-default-vpc --query Vpc.VpcId)
SUBNETS=$(txt ec2 describe-subnets --filters Name=vpc-id,Values="$VPC" Name=default-for-az,Values=true --query 'Subnets[].SubnetId')
SUBNET1=$(echo "$SUBNETS" | awk '{print $1}')

sg_id() { txt ec2 describe-security-groups --filters Name=vpc-id,Values="$VPC" Name=group-name,Values="$1" --query 'SecurityGroups[0].GroupId'; }
WEB_SG=$(sg_id $APP-web)
if [ "$WEB_SG" = None ]; then
  WEB_SG=$(txt ec2 create-security-group --vpc-id "$VPC" --group-name $APP-web --description "edu-apply web: HTTP from CloudFront only" --query GroupId)
  CF_PL=$(txt ec2 describe-managed-prefix-lists --filters Name=prefix-list-name,Values=com.amazonaws.global.cloudfront.origin-facing --query 'PrefixLists[0].PrefixListId')
  aws ec2 authorize-security-group-ingress --group-id "$WEB_SG" \
    --ip-permissions "IpProtocol=tcp,FromPort=80,ToPort=80,PrefixListIds=[{PrefixListId=$CF_PL,Description=CloudFront}]" >/dev/null
fi
DB_SG=$(sg_id $APP-db)
if [ "$DB_SG" = None ]; then
  DB_SG=$(txt ec2 create-security-group --vpc-id "$VPC" --group-name $APP-db --description "edu-apply db: PostgreSQL from web only" --query GroupId)
  aws ec2 authorize-security-group-ingress --group-id "$DB_SG" \
    --ip-permissions "IpProtocol=tcp,FromPort=5432,ToPort=5432,UserIdGroupPairs=[{GroupId=$WEB_SG}]" >/dev/null
fi

say "비밀값 (SSM Parameter Store SecureString, 화면에 찍지 않음)"
put_param secret-key "$(gen_secret 48)"
put_param db-password "$(gen_secret 24)"
put_param demo-admin-password "$(gen_secret 9)"

say "IAM 역할 (SSM 접속 + /$APP/* 파라미터 읽기만)"
if ! aws iam get-role --role-name $APP-ec2 >/dev/null 2>&1; then
  aws iam create-role --role-name $APP-ec2 --assume-role-policy-document file://iam_trust.json >/dev/null
  aws iam attach-role-policy --role-name $APP-ec2 --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
  sed "s/ACCOUNT/$ACCOUNT/; s/REGION/$AWS_REGION/" iam_params.json > .build/iam_params.json
  aws iam put-role-policy --role-name $APP-ec2 --policy-name read-params --policy-document file://.build/iam_params.json
  aws iam create-instance-profile --instance-profile-name $APP-ec2 >/dev/null
  aws iam add-role-to-instance-profile --instance-profile-name $APP-ec2 --role-name $APP-ec2
  sleep 15  # 새 인스턴스 프로필이 EC2에 보일 때까지
fi

say "RDS PostgreSQL 17 (db.t4g.micro, 공개 접근 없음)"
if ! aws rds describe-db-instances --db-instance-identifier $APP-db >/dev/null 2>&1; then
  aws rds describe-db-subnet-groups --db-subnet-group-name $APP >/dev/null 2>&1 || \
    aws rds create-db-subnet-group --db-subnet-group-name $APP --db-subnet-group-description "$APP default VPC" --subnet-ids $SUBNETS >/dev/null
  PG=$(txt rds describe-db-engine-versions --engine postgres --query "DBEngineVersions[?starts_with(EngineVersion,'17.')].EngineVersion | [-1]")
  aws rds create-db-instance --db-instance-identifier $APP-db --engine postgres --engine-version "$PG" \
    --db-instance-class db.t4g.micro --allocated-storage 20 --storage-type gp3 --storage-encrypted \
    --master-username edu \
    --master-user-password "$(txt ssm get-parameter --name /$APP/db-password --with-decryption --query Parameter.Value)" \
    --db-name edu_apply --vpc-security-group-ids "$DB_SG" --db-subnet-group-name $APP \
    --no-publicly-accessible --no-multi-az --backup-retention-period 1 --tags Key=app,Value=$APP >/dev/null
fi

say "EC2 (t4g.small, Amazon Linux 2023 arm64)"
IID=$(instance_id)
if [ "$IID" = None ]; then
  IID=$(txt ec2 run-instances --image-id resolve:ssm:/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64 \
    --instance-type t4g.small --subnet-id "$SUBNET1" --security-group-ids "$WEB_SG" \
    --iam-instance-profile Name=$APP-ec2 --user-data file://user_data.sh \
    --metadata-options HttpTokens=required \
    --block-device-mappings 'DeviceName=/dev/xvda,Ebs={VolumeSize=20,VolumeType=gp3,Encrypted=true}' \
    --tag-specifications "ResourceType=instance,Tags=[{Key=app,Value=$APP},{Key=Name,Value=$APP-web}]" \
    --query 'Instances[0].InstanceId')
fi
aws ec2 wait instance-running --instance-ids "$IID"
EC2_DNS=$(txt ec2 describe-instances --instance-ids "$IID" --query 'Reservations[0].Instances[0].PublicDnsName')

say "CloudFront (https://….cloudfront.net, /static/은 캐시)"
CF_ID=$(txt cloudfront list-distributions --query "DistributionList.Items[?Comment=='$APP'].Id | [0]")
if [ "$CF_ID" = None ]; then
  sed "s/EC2_DNS/$EC2_DNS/g; s/CALLER_REF/$APP-$(date +%s)/" cloudfront.json > .build/cloudfront.json
  CF_ID=$(txt cloudfront create-distribution --distribution-config file://.build/cloudfront.json --query Distribution.Id)
fi
CF_HOST=$(txt cloudfront get-distribution --id "$CF_ID" --query Distribution.DomainName)
put_param public-host "$CF_HOST" overwrite

say "RDS 준비 기다리기 (처음엔 5~10분)"
aws rds wait db-instance-available --db-instance-identifier $APP-db
put_param db-host "$(txt rds describe-db-instances --db-instance-identifier $APP-db --query 'DBInstances[0].Endpoint.Address')" overwrite

run_deploy "$IID"

say "CloudFront 배포 기다리기 (처음엔 5~10분)"
aws cloudfront wait distribution-deployed --id "$CF_ID"
echo
echo "주소: https://$CF_HOST"
echo "관리 화면: https://$CF_HOST/manage/ (계정 demo, 비밀번호는 SSM 파라미터 /$APP/demo-admin-password)"
