from django.urls import path
from django.contrib.auth import views as auth
from pms import views

urlpatterns=[
    path('',views.landing),
    path('login/',views.login_view),path('logout/',views.logout_view),path('setup/',views.setup),path('app/',views.app),
    path('api/vouchers/settlements/',views.settlement_register),
    path('api/checkout/preview/',views.checkout_preview),
    path('api/ledger/',views.ledger_view),path('api/ledger/preview/',views.ledger_preview),
    path('api/birth-date/',views.birth_date),path('api/guest-photo/<int:pk>/',views.photo),
    path('health/',views.health),path('api/state/',views.state),path('api/action/<str:name>/',views.action),path('api/reports/',views.reports),
    path('contract/shared/<str:token>/',views.shared_contract),
    path('export/<str:dataset>/<str:fmt>/',views.export_view),path('document/<str:kind>/<int:pk>/',views.document),
    path('password-reset/',auth.PasswordResetView.as_view(template_name='password_reset.html',email_template_name='reset_email.txt',subject_template_name='reset_subject.txt',success_url='/password-reset/done/')),
    path('password-reset/done/',auth.PasswordResetDoneView.as_view(template_name='reset_done.html')),
    path('reset/<uidb64>/<token>/',auth.PasswordResetConfirmView.as_view(template_name='reset_confirm.html',success_url='/login/'),name='password_reset_confirm'),
]
