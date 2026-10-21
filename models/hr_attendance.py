import base64
import math

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    kiosk_in_photo = fields.Binary(string="Check In Photo", attachment=True, copy=False)
    kiosk_out_photo = fields.Binary(string="Check Out Photo", attachment=True, copy=False)
    kiosk_in_latitude = fields.Float(string="Check In Latitude", digits=(10, 7), copy=False)
    kiosk_in_longitude = fields.Float(string="Check In Longitude", digits=(10, 7), copy=False)
    kiosk_out_latitude = fields.Float(string="Check Out Latitude", digits=(10, 7), copy=False)
    kiosk_out_longitude = fields.Float(string="Check Out Longitude", digits=(10, 7), copy=False)
    kiosk_in_accuracy = fields.Float(string="Check In GPS Accuracy (m)", copy=False)
    kiosk_out_accuracy = fields.Float(string="Check Out GPS Accuracy (m)", copy=False)

    @api.model
    def _kiosk_get_config(self):
        company = self.env.company
        lat = company.attendance_kiosk_office_latitude
        lon = company.attendance_kiosk_office_longitude
        radius = company.attendance_kiosk_office_radius or 50.0
        if not lat and not lon:
            raise UserError(_("Office GPS coordinates are not configured. Ask an Attendance administrator."))
        lat, lon, radius = float(lat), float(lon), float(radius)
        if not (-90 <= lat <= 90 and -180 <= lon <= 180 and 1 <= radius <= 5000):
            raise UserError(_("The office GPS configuration is outside the permitted range."))
        return {"latitude": lat, "longitude": lon, "radius": radius}

    @api.model
    def _kiosk_configured(self):
        company = self.env.company
        params = self.env["ir.config_parameter"].sudo()
        prefix = "attendance_kiosk_custom."
        return bool(
            params.get_param(prefix + "office_latitude_" + str(company.id), "") != ""
            and params.get_param(prefix + "office_longitude_" + str(company.id), "") != ""
        )

    @api.model
    def _kiosk_distance_meters(self, lat1, lon1, lat2, lon2):
        earth_radius = 6371000.0
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
        a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
        return earth_radius * 2 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1 - a)))

    @api.model
    def kiosk_get_status(self):
        employee = self.env.user.employee_id
        if not employee:
            raise UserError(_("Your Odoo user is not linked to an employee. Ask HR to configure it."))
        if employee.company_id not in self.env.companies:
            raise AccessError(_("You do not have access to this employee's company."))
        attendance = self.sudo().search([
            ("employee_id", "=", employee.id), ("check_out", "=", False)
        ], order="check_in desc", limit=1)
        return {
            "employee_name": employee.name,
            "checked_in": bool(attendance),
            "check_in": fields.Datetime.to_string(attendance.check_in) if attendance else False,
            "office_configured": self._kiosk_configured(),
        }

    @api.model
    def kiosk_submit_attendance(self, action, photo_data, latitude, longitude, accuracy):
        if action not in ("check_in", "check_out"):
            raise ValidationError(_("Invalid attendance action."))
        employee = self.env.user.employee_id
        if not employee:
            raise UserError(_("Your Odoo user is not linked to an employee. Ask HR to configure it."))
        if employee.company_id not in self.env.companies:
            raise AccessError(_("You do not have access to this employee's company."))

        if not isinstance(photo_data, str) or not photo_data.startswith("data:image/jpeg;base64,"):
            raise ValidationError(_("A camera photo is required for every check in and check out."))
        try:
            photo = base64.b64decode(photo_data.split(",", 1)[1], validate=True)
        except Exception:
            raise ValidationError(_("The camera image could not be read. Please capture it again."))
        if not photo or len(photo) > 8 * 1024 * 1024:
            raise ValidationError(_("The photo is empty or too large. Maximum size is 8 MB."))

        try:
            latitude, longitude, accuracy = float(latitude), float(longitude), float(accuracy)
        except (TypeError, ValueError):
            raise ValidationError(_("A valid GPS location is required."))
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValidationError(_("The GPS coordinates are invalid."))
        if accuracy < 0 or accuracy > 100:
            raise UserError(_("GPS accuracy is too low. Enable precise location and retry."))

        config = self._kiosk_get_config()
        distance = self._kiosk_distance_meters(latitude, longitude, config["latitude"], config["longitude"])
        if distance > config["radius"]:
            raise UserError(_(
                "Attendance rejected: you are approximately %(distance).1f meters from the office. "
                "You must be within %(radius)s meters.",
                distance=distance, radius=config["radius"]
            ))

        Attendance = self.sudo()
        open_attendance = Attendance.search([
            ("employee_id", "=", employee.id), ("check_out", "=", False)
        ], order="check_in desc", limit=1)

        if action == "check_in":
            if open_attendance:
                raise UserError(_("You are already checked in. Check out before starting another attendance."))
            Attendance.create({
                "employee_id": employee.id,
                "check_in": fields.Datetime.now(),
                "kiosk_in_photo": base64.b64encode(photo),
                "kiosk_in_latitude": latitude,
                "kiosk_in_longitude": longitude,
                "kiosk_in_accuracy": accuracy,
            })
            return {"success": True, "message": _("Check In recorded successfully.")}

        if not open_attendance:
            raise UserError(_("You are not currently checked in."))
        open_attendance.write({
            "check_out": fields.Datetime.now(),
            "kiosk_out_photo": base64.b64encode(photo),
            "kiosk_out_latitude": latitude,
            "kiosk_out_longitude": longitude,
            "kiosk_out_accuracy": accuracy,
        })
        return {"success": True, "message": _("Check Out recorded successfully.")}
