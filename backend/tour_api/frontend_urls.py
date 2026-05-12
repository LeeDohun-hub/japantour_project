"""루트·정적 JS/CSS (API 경로와 분리)."""

from django.urls import path

from tour_api import views

urlpatterns = [
    path("chat/", views.serve_chat, name="chat_page"),
    path("styles.css", views.serve_styles),
    path("app.js", views.serve_app_js),
    path("", views.serve_home, name="home_page"),
]
