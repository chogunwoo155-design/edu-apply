#!/bin/bash
# EC2 첫 부팅: Docker·git 설치, 공개 저장소 받기. 실제 배포는 server_deploy.sh가 한다.
set -euxo pipefail
dnf install -y docker git
systemctl enable --now docker
git clone https://github.com/chogunwoo155-design/edu-apply.git /opt/edu-apply
