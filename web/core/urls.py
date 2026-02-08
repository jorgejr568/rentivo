from django.urls import path

from . import views

urlpatterns = [
    path("", views.billing_list, name="billing_list"),
    path("billings/create/", views.billing_create, name="billing_create"),
    path("billings/<int:billing_id>/", views.billing_detail, name="billing_detail"),
    path("billings/<int:billing_id>/edit/", views.billing_edit, name="billing_edit"),
    path("billings/<int:billing_id>/delete/", views.billing_delete, name="billing_delete"),
    path("billings/<int:billing_id>/generate/", views.bill_generate, name="bill_generate"),
    path("bills/<int:bill_id>/", views.bill_detail, name="bill_detail"),
    path("bills/<int:bill_id>/edit/", views.bill_edit, name="bill_edit"),
    path("bills/<int:bill_id>/invoice/", views.bill_invoice, name="bill_invoice"),
]
