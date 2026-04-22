from django.urls import path
from . import views

urlpatterns = [
    path("",                    views.index),
    path("predict/",            views.run_prediction),
    path("history/",            views.get_history),
    path("stats/",              views.get_stats),
    path("admin-upload/",       views.admin_upload),
    path("admin-retrain/",      views.admin_retrain),
    path("admin-model/",        views.admin_model_info),
    path("admin-login/",        views.admin_login),
    path("admin-create-user/",  views.admin_create_user),
    path("admin-verify/",       views.admin_verify_token),
]