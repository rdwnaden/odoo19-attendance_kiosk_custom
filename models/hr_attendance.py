
import base64
import math

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    kiosk_in_photo = fields.Binary(string="Check In Photo",attachment=True,copy=False)
    kiosk_out_photo = fields.Binary(string="Check Out Photo",attachment=True,copy=False)
    kiosk_in_latitude = fields.Float(string="Check In Latitude",digits=(10, 7),copy=False)
    kiosk_in_longitude = fields.Float(string="Check In Longitude",digits=(10, 7),copy=False)
    kiosk_out_latitude = fields.Float(string="Check Out Latitude",digits=(10, 7),copy=False)
    kiosk_out_longitude = fields.Float(string="Check Out Longitude",digits=(10, 7),copy=False)
    kiosk_in_accuracy = fields.Float(string="Check In GPS Accuracy (m)",copy=False)
    kiosk_out_accuracy = fields.Float(string="Check Out GPS Accuracy (m)",copy=False)

    # =========================================================
    # OFFICE CONFIGURATION
    # =========================================================

    @api.model
    def _kiosk_get_config(self):
        company = self.env.company

        lat = company.attendance_kiosk_office_latitude
        lon = company.attendance_kiosk_office_longitude
        radius = company.attendance_kiosk_office_radius or 50.0

        if not lat and not lon:
            raise UserError(_(
                "Office GPS coordinates are not configured. "
                "Ask an Attendance administrator."
            ))

        lat = float(lat)
        lon = float(lon)
        radius = float(radius)

        if not (
            -90 <= lat <= 90
            and -180 <= lon <= 180
            and 1 <= radius <= 5000
        ):
            raise UserError(_(
                "The office GPS configuration is invalid. "
                "Check the office latitude, longitude, and radius."
            ))

        return {
            "latitude": lat,
            "longitude": lon,
            "radius": radius,
        }

    @api.model
    def _kiosk_configured(self):
        """Use the same company fields as the actual GPS validation."""
        company = self.env.company

        lat = company.attendance_kiosk_office_latitude
        lon = company.attendance_kiosk_office_longitude

        return bool(lat or lon)

    @api.model
    def _kiosk_distance_meters(self, lat1, lon1, lat2, lon2):
        earth_radius = 6371000.0

        p1 = math.radians(lat1)
        p2 = math.radians(lat2)

        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)

        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(p1)
            * math.cos(p2)
            * math.sin(dlon / 2) ** 2
        )

        a = max(0.0, min(1.0, a))

        return earth_radius * 2 * math.atan2(
            math.sqrt(a),
            math.sqrt(1.0 - a),
        )

    # =========================================================
    # ATTENDANCE STATUS
    # =========================================================

    @api.model
    def kiosk_get_status(self):
        employee = self.env.user.employee_id

        if not employee:
            raise UserError(_(
                "Your Odoo user is not linked to an employee. "
                "Ask HR to configure it."
            ))

        if employee.company_id not in self.env.companies:
            raise AccessError(_(
                "You do not have access to this employee's company."
            ))

        attendance = self.sudo().search([
            ("employee_id", "=", employee.id),
            ("check_out", "=", False),
        ], order="check_in desc", limit=1)

        return {
            "employee_name": employee.name,
            "checked_in": bool(attendance),
            "check_in": (
                fields.Datetime.to_string(attendance.check_in)
                if attendance else False
            ),
            "office_configured": self._kiosk_configured(),
        }

    # =========================================================
    # SUBMIT CHECK IN / CHECK OUT
    # =========================================================

    @api.model
    def kiosk_submit_attendance(
        self,
        action,
        photo_data,
        latitude,
        longitude,
        accuracy,
    ):
        if action not in ("check_in", "check_out"):
            raise ValidationError(_("Invalid attendance action."))

        employee = self.env.user.employee_id

        if not employee:
            raise UserError(_(
                "Your Odoo user is not linked to an employee. "
                "Ask HR to configure it."
            ))

        if employee.company_id not in self.env.companies:
            raise AccessError(_(
                "You do not have access to this employee's company."
            ))

        # -----------------------------------------------------
        # Validate photo
        # -----------------------------------------------------

        prefix = "data:image/jpeg;base64,"

        if (
            not isinstance(photo_data, str)
            or not photo_data.startswith(prefix)
        ):
            raise ValidationError(_(
                "A camera photo is required for every check in "
                "and check out. Please capture the photo again."
            ))

        try:
            photo = base64.b64decode(
                photo_data.split(",", 1)[1],
                validate=True,
            )
        except Exception:
            raise ValidationError(_(
                "The camera image could not be read. "
                "Please capture it again."
            ))

        if not photo:
            raise ValidationError(_("The captured photo is empty."))

        if len(photo) > 8 * 1024 * 1024:
            raise ValidationError(_(
                "The photo is too large. Maximum size is 8 MB."
            ))

        # -----------------------------------------------------
        # Validate GPS values
        # -----------------------------------------------------

        try:
            latitude = float(latitude)
            longitude = float(longitude)
            accuracy = float(accuracy)
        except (TypeError, ValueError):
            raise ValidationError(_(
                "A valid GPS location is required. "
                "Please retrieve your location again."
            ))

        if not (
            math.isfinite(latitude)
            and math.isfinite(longitude)
            and math.isfinite(accuracy)
        ):
            raise ValidationError(_("The GPS values are invalid."))

        if not (
            -90 <= latitude <= 90
            and -180 <= longitude <= 180
        ):
            raise ValidationError(_("The GPS coordinates are invalid."))

        if accuracy < 0 or accuracy > 100:
            raise UserError(_(
                "GPS accuracy is too low. Enable precise location "
                "and retry. Current accuracy: %(accuracy).1f meters.",
                accuracy=accuracy,
            ))

        # -----------------------------------------------------
        # Validate office radius on the server
        # -----------------------------------------------------

        config = self._kiosk_get_config()

        distance = self._kiosk_distance_meters(
            latitude,
            longitude,
            config["latitude"],
            config["longitude"],
        )

        if distance > config["radius"]:
            raise UserError(_(
                "Attendance rejected: you are approximately "
                "%(distance).1f meters from the office. "
                "You must be within %(radius).1f meters.",
                distance=distance,
                radius=config["radius"],
            ))

        # -----------------------------------------------------
        # Find existing open attendance
        # -----------------------------------------------------

        Attendance = self.sudo()

        open_attendance = Attendance.search([
            ("employee_id", "=", employee.id),
            ("check_out", "=", False),
        ], order="check_in desc", limit=1)

        # -----------------------------------------------------
        # CHECK IN
        # -----------------------------------------------------

        if action == "check_in":
            if open_attendance:
                raise UserError(_(
                    "You are already checked in. "
                    "Check out before starting another attendance."
                ))

            attendance = Attendance.create({
                "employee_id": employee.id,
                "check_in": fields.Datetime.now(),
                "kiosk_in_photo": base64.b64encode(photo),
                "kiosk_in_latitude": latitude,
                "kiosk_in_longitude": longitude,
                "kiosk_in_accuracy": accuracy,
            })

            return {
                "success": True,
                "action": "check_in",
                "attendance_id": attendance.id,
                "checked_in": True,
                "message": _("Check In recorded successfully."),
            }

        # -----------------------------------------------------
        # CHECK OUT
        # -----------------------------------------------------

        if not open_attendance:
            raise UserError(_(
                "You are not currently checked in. "
                "Refresh the attendance status and try again."
            ))

        open_attendance.write({
            "check_out": fields.Datetime.now(),
            "kiosk_out_photo": base64.b64encode(photo),
            "kiosk_out_latitude": latitude,
            "kiosk_out_longitude": longitude,
            "kiosk_out_accuracy": accuracy,
        })

        return {
            "success": True,
            "action": "check_out",
            "attendance_id": open_attendance.id,
            "checked_in": False,
            "message": _("Check Out recorded successfully."),
        }
