from django.urls import path
from fam import views, views_printing, views_printing_2

app_name = 'fam'

urlpatterns = [

    path('', views.fam, name='fam'),
    path('qr_tags/', views.tag_admin, name='tag_admin'),
    path('qr_batch_create/', views.batch_create_labels, name='batch_create_labels'),

    path('print_labels/', views.print_labels, name='print_labels'),
    path('print_labels/template_selector/', views.fam_label_template_preview, name='fam_label_template_preview'),

    path('labels/designer/', views.label_designer, name='label_designer'),
    path('labels/<uuid:id>/assign', views.assign_label, name='assign_label'),
    path("layouts/<int:id>/logo/upload/", views_printing.layout_logo_upload, name="layout_logo_upload"),

    path('register_scan/', views.asset_scan_log, name='register_scan'),
    path('myassets', views.dashboard, name='myassets'),
    path('asset_details/<str:fam_label_id>', views.asset_details, name='asset_details'),

    path('asset_admin/', views.asset_admin, name='asset_admin'),
    path('create_asset/', views.create_asset, name='create_asset'),
    path('asset_import/', views.asset_import, name="asset_import"),
    path('create_labels/', views.batch_create_labels, name='batch_create_labels'),

    path('print_labels/filter/', views.fam_label_filter, name='fam_label_filter'),
    path('generate_pdf', views.generate_pdf, name='generate_pdf'),

    path('tables/brand/', views.brand_crud, name='brand_crud'),
    path('tables/policy/', views.policy_crud, name='policy_crud'),
    path('tables/asset_type/', views.asset_type_crud, name='asset_type_crud'),
    path('tables/asset_type/<int:id>', views.asset_type_crud, name='asset_type_crud_edit'),


    path('fam/kpis/', views.refresh_kpis, name='refresh-kpis'),
    path('fam/list/', views.list_assets, name='list_assets'),

    # - GET -> renders Print Format modal (list + create/edit form)
    # - POST with action=save|disable|enable -> persists changes and re-renders modal
    # - POST with action=preview_png -> returns a PNG (used mainly by XHR, not <img>)
    # path("print-formats/", views.print_formats, name="print_formats"),

    # Lightweight GET previews (handy for <img src="..."> in templates):
    # path("print-format/preview.png", views.print_format_preview_png, name="print_format_preview_png"),
    # path("layout/preview.png",       views.layout_preview_png,       name="layout_preview_png"),

    # path("labels/print/preview", views.print_format_preview, name="print_format_preview"),

    path("layouts/picker", views_printing.layout_picker, name="layout_picker"),
    path("layouts/preview.png", views_printing.layout_preview_png, name="layout_preview_png"),
    path("formats/configuration/", views_printing.print_format_configuration, name="print_format_configuration"),

    path("formats/save", views_printing.print_format_save, name="print_format_save"),
    path("formats/delete", views_printing.print_format_delete, name="print_format_delete"),
    path("formats/preview.png", views_printing.print_format_preview_png, name="print_format_preview_png"),
    # path("labels/print/pdf", views_printing.print_labels_with_format_pdf, name="print_labels_with_format_pdf"),

    path("formats/page_preview", views_printing_2.print_format_page_preview, name="print_format_page_preview"),
    # path("formats/page_preview.png", views_printing_2.print_format_page_preview_png, name="print_format_page_preview_png"),
    path("formats/page_preview.pdf", views_printing_2.print_format_page_preview_pdf, name="print_format_page_preview_pdf"),
    path("formats/page_preview.fragment", views_printing_2.print_format_page_preview_fragment, name="print_format_page_preview_fragment"),
]


