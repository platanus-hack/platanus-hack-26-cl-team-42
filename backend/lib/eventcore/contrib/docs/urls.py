from django.urls import path

from .views import graph_view

app_name = "eventcore_docs"

urlpatterns = [
    path("", graph_view, name="graph"),
]
