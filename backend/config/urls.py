from django.urls import include, path

urlpatterns = [
    path("api/", include("tour_api.urls")),
    path("", include("tour_api.frontend_urls")),
]
