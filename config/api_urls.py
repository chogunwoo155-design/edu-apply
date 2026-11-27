from rest_framework.routers import DefaultRouter

from applications.api import ApplicationViewSet
from courses.api import CourseViewSet

router = DefaultRouter()
router.register("courses", CourseViewSet, basename="course")
router.register("applications", ApplicationViewSet, basename="application")

urlpatterns = router.urls
