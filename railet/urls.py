# SPDX-License-Identifier: MPL-2.0
from django.urls import path
from django.contrib.auth import views as auth
from inventory import views
from customers import views as customers
from deals import views as deals
from deals import trade_views
from deals import review_views
from deals import lifecycle
from deals import history_views
from deals import followups
from documents import views as documents
from documents import packet_views
from documents import packet_exports
from core import filter_views
from feedback import views as feedback
from finance import views as finance
from finance import schedule_views
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

urlpatterns += [
    path("feedback/", feedback.report_list, name="feedback_list"),
    path("feedback/new/", feedback.report_create, name="feedback_create"),
    path("feedback/confirm/", feedback.report_confirm, name="feedback_confirm"),
    path("feedback/<int:pk>/", feedback.report_detail, name="feedback_detail"),
]

urlpatterns += [
    path("deals/<int:pk>/demo-packets/", packet_views.packet_list, name="demo_packet_list"),
    path("deals/<int:pk>/demo-packets/<int:packet_pk>/", packet_views.packet_detail, name="demo_packet_detail"),
    path("deals/<int:pk>/demo-packets/<int:packet_pk>/artifact/", packet_views.packet_artifact, name="demo_packet_artifact"),
]

urlpatterns += [path("deals/<int:pk>/archive-state/", lifecycle.change_state, name="draft_lifecycle")]

urlpatterns += [path("deals/<int:pk>/history/", history_views.deal_history, name="deal_history")]

urlpatterns += [path("deals/<int:pk>/demo-packets/<int:packet_pk>/export/", packet_exports.packet_export, name="demo_packet_export")]

urlpatterns += [
    path("follow-ups/", followups.listing, name="followups"),
    path("follow-ups/<int:pk>/", followups.detail, name="followup_detail"),
    path("deals/<int:pk>/follow-ups/new/", followups.editor, name="followup_create"),
    path("deals/<int:pk>/follow-ups/<int:task_pk>/edit/", followups.editor, name="followup_edit"),
]

urlpatterns += [
    path("ledger-demo/", finance.listing, name="ledger_demo_list"),
    path("ledger-demo/new/", finance.prepare, {"kind":"opening"}, name="ledger_demo_new"),
    path("ledger-demo/confirm/", finance.confirm, name="ledger_demo_confirm"),
    path("ledger-demo/<int:pk>/", finance.detail, name="ledger_demo_detail"),
    path("ledger-demo/<int:pk>/receipt/", finance.prepare, {"kind":"receipt"}, name="ledger_demo_receipt"),
    path("ledger-demo/<int:pk>/reverse/<int:posting_pk>/", finance.prepare, {"kind":"reversal"}, name="ledger_demo_reverse"),
]

urlpatterns += [
    path("ledger-demo/<int:pk>/schedules/", schedule_views.listing, name="schedule_list"),
    path("ledger-demo/<int:pk>/schedules/new/", schedule_views.prepare, name="schedule_new"),
    path("ledger-demo/schedules/confirm/", schedule_views.confirm, name="schedule_confirm"),
    path("ledger-demo/<int:pk>/schedules/<int:scenario_pk>/", schedule_views.detail, name="schedule_detail"),
]

from finance import account_views
urlpatterns += [
    path('bhph-demo/<int:pk>/', account_views.workspace, name='bhph_account'),
    path('bhph-demo/<int:pk>/link/', account_views.link, name='bhph_account_link'),
    path('bhph-demo/<int:pk>/receipts/<int:posting_pk>/', account_views.receipt, name='bhph_account_receipt'),
]

from finance import opening_views
urlpatterns += [path('deals/<int:pk>/demo-account/', opening_views.opening, name='draft_demo_account')]

from finance import account_exports
urlpatterns += [
    path('bhph-demo/<int:pk>/export/', account_exports.review, name='account_export_review'),
    path('bhph-demo/<int:pk>/export/download/', account_exports.download, name='account_export_download'),
]

from finance import payment_register
urlpatterns += [path('ledger-demo/payments/', payment_register.register, name='payment_register')]

from finance import servicing_views
urlpatterns += [path('bhph-demo/<int:pk>/servicing/setup/',servicing_views.setup,name='servicing_setup'),path('bhph-demo/<int:pk>/servicing/',servicing_views.detail,name='servicing_detail')]

from deals import desking_views
urlpatterns += [path('deals/estimate/',desking_views.preview,name='deal_estimate')]
