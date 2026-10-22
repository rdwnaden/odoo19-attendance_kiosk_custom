{
    "name": "Attendance Kiosk Custom",
    "version": "19.0.1.0.0",
    "category": "Human Resources/Attendances",
    "summary": "Attendance check-in/out with required camera photo and GPS geofence",
    "description": "Custom My Attendance page with camera capture and server-side 50-meter GPS validation.",
    "author": "Ridwan Aden",
    "license": "LGPL-3",
    "depends": ["hr_attendance", "web"],
    "data": [
        "security/attendance_kiosk_security.xml",
        "views/attendance_kiosk_views.xml",
        "views/res_config_settings_views.xml",
        "views/hr_attendance_views.xml"
    ],
    "assets": {
        "web.assets_backend": [
            "attendance_kiosk_custom/static/src/js/my_attendance.js",
            "attendance_kiosk_custom/static/src/xml/my_attendance.xml",
            "attendance_kiosk_custom/static/src/scss/my_attendance.scss"
        ]
    },
    "installable": True,
    "application": True
}
