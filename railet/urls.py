# SPDX-License-Identifier: MPL-2.0
from django.urls import path
from django.contrib.auth import views as auth
from inventory import views
from customers import views as customers
from deals import views as deals
from deals import trade_views
from deals import review_views
from documents import views as documents
from core import filter_views
urlpatterns = [path("accounts/login/", auth.LoginView.as_view(), name="login"), path("accounts/logout/", auth.LogoutView.as_view(), name="logout"), path("", views.today, name="today"), path("inventory/", views.vehicle_list, name="inventory"), path("inventory/new/", views.vehicle_create, name="vehicle_create"), path("inventory/<int:pk>/", views.vehicle_detail, name="vehicle_detail"), path("inventory/<int:pk>/edit/", views.vehicle_edit, name="vehicle_edit")]

urlpatterns += [
    path("deals/<int:pk>/files/", documents.deal_files, name="deal_files"),
    path("deals/<int:pk>/files/<int:file_pk>/action/", documents.file_action, name="deal_file_action"),
    path("deals/<int:pk>/files/<int:file_pk>/download/", documents.file_download, name="deal_file_download"),
    path("deals/<int:pk>/review/", review_views.review_detail, name="deal_review"),
    path("deals/<int:pk>/trade/", trade_views.trade_edit, name="trade_edit"),
    path("deals/<int:pk>/trade/<int:trade_pk>/remove/", trade_views.trade_remove, name="trade_remove"),
    path("deals/<int:pk>/trade/<int:trade_pk>/intake/", trade_views.trade_intake, name="trade_intake"),
    path("views/<slug:resource>/new/", filter_views.saved_view_create, name="saved_view_create"),
    path("views/<int:pk>/delete/", filter_views.saved_view_delete, name="saved_view_delete"),
    path("inventory/<int:pk>/photos/", views.vehicle_photo_upload, name="vehicle_photo_upload"),
    path("inventory/photos/<int:pk>/", views.vehicle_photo_file, name="vehicle_photo_file"),
    path("inventory/photos/<int:pk>/thumbnail/", views.vehicle_photo_file, {"thumbnail": True}, name="vehicle_photo_thumbnail"),
    path("inventory/photos/<int:pk>/action/", views.vehicle_photo_action, name="vehicle_photo_action"),
    path("customers/", customers.customer_list, name="customers"),
    path("customers/new/", customers.customer_create, name="customer_create"),
    path("customers/<int:pk>/", customers.customer_detail, name="customer_detail"),
    path("customers/<int:pk>/edit/", customers.customer_edit, name="customer_edit"),
    path("deals/", deals.deal_list, name="deals"),
    path("deals/new/", deals.deal_create, name="deal_create"),
    path("deals/<int:pk>/", deals.deal_detail, name="deal_detail"),
    path("deals/<int:pk>/edit/", deals.deal_edit, name="deal_edit"),
]
