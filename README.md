# Attendance Kiosk Custom — Odoo 19 CE

## Features
- Adds Attendances > My Attendance.
- Requires a new camera photo for every check in and check out.
- Requires browser GPS coordinates and GPS accuracy <= 100 meters.
- Server validates distance to the office with the Haversine formula; default radius is 50 meters.
- Saves photos, latitude, longitude, and GPS accuracy on `hr.attendance`.
- Employee identity is derived from the logged-in Odoo user, not a browser-supplied employee ID.

## Installation
1. Back up the database first.
2. Copy `attendance_kiosk_custom` into an addons directory included in `addons_path`.
3. Restart Odoo.
4. Update the Apps list and install **Attendance Kiosk Custom**.
5. Open Attendances > Configuration > Settings.
6. Set office latitude and longitude in **My Attendance GPS Kiosk**. Set radius.
7. Link each employee to their Odoo user.
8. Open Attendances > My Attendance.

## Browser requirements
Camera and geolocation normally require HTTPS, except localhost. Allow camera and location permissions for the Odoo site. GPS can be inaccurate indoors.

## Security and limitations
- The server validates the geofence again; client-side checks are only for user feedback.
- Browser GPS is not spoof-proof on compromised devices.
- Photos are stored as Odoo attachments and may contain personal data. Apply suitable access, retention, and privacy policies.
- Configure each company separately. Test on a staging database first.
- Verify the inherited settings view ID and attendance menu external ID against your exact Odoo 19 build if they have been customized.

## Testing checklist
- Outside office location request is rejected.
- Missing photo or GPS: request is rejected.
- Repeated check-in: rejected.
- Check-out without open attendance: rejected.
- Verify photos and coordinates on the resulting `hr.attendance` record.
