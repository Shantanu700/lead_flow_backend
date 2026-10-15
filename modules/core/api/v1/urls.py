from django.urls import path

from modules.core.api.v1.views import CsrfAV, LoginAV, RegisterAV

urlpatterns = [
    path("csrf/", CsrfAV.as_view()),
    path("login/", LoginAV.as_view()),
    path("register/", RegisterAV.as_view()),
]
