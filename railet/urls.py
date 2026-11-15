# SPDX-License-Identifier: MPL-2.0
from django.urls import path
from django.contrib.auth import views as auth
from inventory import views
from customers import views as customers
from customers import export_views as customer_exports
from deals import views as deals
from deals import trade_views
from deals import review_views
from deals import lifecycle
from deals import history_views
from deals import followups
from documents import views as documents
from documents import acquisition_views
from documents import invoice_views
from documents import packet_views
from documents import packet_exports
from core import dealership_export_views
from core import filter_views
from feedback import views as feedback
from finance import views as finance
from finance import schedule_views
urlpatterns = [path("accounts/login/", auth.LoginView.as_view(), name="login"), path("accounts/logout/", auth.LogoutView.as_view(), name="logout"), path("", views.today, name="today"), path("inventory/", views.vehicle_list, name="inventory"), path("inventory/new/", views.vehicle_create, name="vehicle_create"), path("inventory/<int:pk>/", views.vehicle_detail, name="vehicle_detail"), path("inventory/<int:pk>/edit/", views.vehicle_edit, name="vehicle_edit")]
urlpatterns += [path('inventory/reports/duplicate-vins/', views.duplicate_vin_report, name='duplicate_vin_report')]

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
    path("customers/export/", customer_exports.review, name="customer_export_review"),
    path("customers/export/download/", customer_exports.download, name="customer_export_download"),
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
    path("deals/<int:pk>/demo-packets/<int:packet_pk>/title-practice/", packet_views.title_practice, name="title_practice"),
    path("deals/<int:pk>/demo-packets/<int:packet_pk>/paperwork-review/", packet_views.paperwork_review, name="paperwork_review"),
    path("deals/<int:pk>/demo-packets/<int:packet_pk>/finance-practice/", packet_views.finance_practice, name="finance_practice"),
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

from inventory import recon_views
urlpatterns += [
    path('inventory/<int:pk>/reconditioning/', recon_views.workspace, name='vehicle_recon'),
    path('inventory/<int:pk>/reconditioning/work/new/', recon_views.create, {'kind': 'task'}, name='recon_task_create'),
    path('inventory/<int:pk>/reconditioning/work/<int:task_pk>/edit/', recon_views.task_edit, name='recon_task_edit'),
    path('inventory/<int:pk>/reconditioning/costs/new/', recon_views.create, {'kind': 'cost'}, name='vehicle_cost_create'),
    path('inventory/<int:pk>/reconditioning/work/<int:task_pk>/status/', recon_views.task_status, name='recon_task_status'),
    path('inventory/<int:pk>/reconditioning/costs/<int:entry_pk>/reverse/', recon_views.correction, name='vehicle_cost_reverse'),
]

urlpatterns += [
    path('inventory/reconditioning/', recon_views.queue, name='recon_queue'),
    path('inventory/reconditioning/export.csv', recon_views.queue_export, name='recon_queue_export'),
    path('inventory/vendors/', recon_views.vendor_list, name='vendor_list'),
    path('inventory/vendors/new/', recon_views.vendor_editor, name='vendor_create'),
    path('inventory/vendors/<int:vendor_pk>/', recon_views.vendor_detail, name='vendor_detail'),
    path('inventory/vendors/<int:vendor_pk>/edit/', recon_views.vendor_editor, name='vendor_edit'),
]

from deals import completion_views
urlpatterns += [
    path('deals/<int:pk>/completion/review/',completion_views.prepare,name='deal_completion_prepare'),
    path('deals/<int:pk>/completion/',completion_views.detail,name='deal_completion'),
    path('deals/<int:pk>/completion/void/',completion_views.void_review,name='deal_completion_void'),
    path('deals/<int:pk>/completion/follow-on/',completion_views.follow_on_review,name='deal_completion_follow_on'),
]

from customers import activity as customer_activity
urlpatterns += [path('customers/<int:pk>/activity/new/',customer_activity.create,name='customer_activity_create'),
                path('customers/<int:pk>/activity/<int:activity_pk>/complete/',customer_activity.complete,name='customer_activity_complete')]
urlpatterns += [path('customer-activity/', customer_activity.queue, name='customer_activity_queue')]

from inventory import reports as inventory_reports
urlpatterns += [
    path('inventory/reports/investment/', inventory_reports.investment_report, name='inventory_investment_report'),
    path('inventory/reports/investment/export.csv', inventory_reports.investment_report_export, name='inventory_investment_report_export'),
]
urlpatterns += [path('customers/<int:pk>/activity/<int:activity_pk>/edit/',customer_activity.edit,name='customer_activity_edit')]
urlpatterns += [path('customers/<int:pk>/activity/', customer_activity.history, name='customer_activity_history')]

urlpatterns += [
    path("inventory/<int:pk>/invoices/", invoice_views.invoices, name="vehicle_invoices"),
    path("inventory/<int:pk>/invoices/<int:invoice_pk>/download/", invoice_views.download, name="vehicle_invoice_download"),
    path("inventory/<int:pk>/acquisition-files/", acquisition_views.acquisition_files, name="vehicle_acquisition_files"),
    path("inventory/<int:pk>/acquisition-files/<int:file_pk>/action/", acquisition_views.acquisition_file_action, name="vehicle_acquisition_file_action"),
    path("inventory/<int:pk>/acquisition-files/<int:file_pk>/download/", acquisition_views.acquisition_file_download, name="vehicle_acquisition_file_download"),
]

urlpatterns += [
    path("dealership/export/", dealership_export_views.review, name="dealership_export_review"),
    path("dealership/export/download/", dealership_export_views.download, name="dealership_export_download"),
]
