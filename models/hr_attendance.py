
import base64
import math

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    # =========================================================
    # ATTENDANCE PHOTO
    # =========================================================

    kiosk_in_photo = fields.Image(
        string="Check In Photo",
        max_width=1920,
        max_height=1920,
        attachment=True,
        copy=False,
    )

    kiosk_out_photo = fields.Image(
        string="Check Out Photo",
        max_width=1920,
        max_height=1920,
        attachment=True,
        copy=False,
    )

    # =========================================================
    # GPS COORDINATES
    # =========================================================

    kiosk_in_latitude = fields.Float(
        string="Check In Latitude",
        digits=(10, 7),
        copy=False,
    )

    kiosk_in_longitude = fields.Float(
        string="Check In Longitude",
        digits=(10, 7),
        copy=False,
    )

    kiosk_out_latitude = fields.Float(
        string="Check Out Latitude",
        digits=(10, 7),
        copy=False,
    )

    kiosk_out_longitude = fields.Float(
        string="Check Out Longitude",
        digits=(10, 7),
        copy=False,
    )

    kiosk_in_accuracy = fields.Float(
        string="Check In GPS Accuracy (m)",
        copy=False,
    )

    kiosk_out_accuracy = fields.Float(
        string="Check Out GPS Accuracy (m)",
        copy=False,
    )

    # =========================================================
    # BROWSER / DEVICE AND IP ADDRESS
    # =========================================================

    kiosk_in_browser = fields.Char(
        string="Check In Browser / Device",
        readonly=True,
        copy=False,
    )

    kiosk_out_browser = fields.Char(
        string="Check Out Browser / Device",
        readonly=True,
        copy=False,
    )

    kiosk_in_ip = fields.Char(
        string="Check In IP Address",
        readonly=True,
        copy=False,
    )

    kiosk_out_ip = fields.Char(
        string="Check Out IP Address",
        readonly=True,
        copy=False,
    )

    # =========================================================
    # GOOGLE MAPS
    # =========================================================

    kiosk_show_in_map = fields.Boolean(
        string="Show Check In Map",
        default=False,
        copy=False,
    )

    kiosk_show_out_map = fields.Boolean(
        string="Show Check Out Map",
        default=False,
        copy=False,
    )

    kiosk_in_map_html = fields.Html(
        string="Check In Map",
        compute="_compute_kiosk_map_html",
        sanitize=False,
        readonly=True,
    )

    kiosk_out_map_html = fields.Html(
        string="Check Out Map",
        compute="_compute_kiosk_map_html",
        sanitize=False,
        readonly=True,
    )

    @api.depends(
        "kiosk_in_latitude",
        "kiosk_in_longitude",
        "kiosk_out_latitude",
        "kiosk_out_longitude",
    )
    def _compute_kiosk_map_html(self):
        for attendance in self:
            attendance.kiosk_in_map_html = False
            attendance.kiosk_out_map_html = False

            # Check In map: always visible when coordinates exist
            in_lat = attendance.kiosk_in_latitude
            in_lon = attendance.kiosk_in_longitude

            if (
                (in_lat or in_lon)
                and -90 <= in_lat <= 90
                and -180 <= in_lon <= 180
            ):
                attendance.kiosk_in_map_html = (
                    '<iframe '
                    'width="100%" height="160" '
                    'style="border:0; display:block;" '
                    'loading="lazy" '
                    'referrerpolicy="no-referrer-when-downgrade" '
                    'allowfullscreen '
                    'src="https://maps.google.com/maps?'
                    f'q={in_lat:.7f},{in_lon:.7f}&output=embed">'
                    '</iframe>'
                )

            # Check Out map: always visible when coordinates exist
            out_lat = attendance.kiosk_out_latitude
            out_lon = attendance.kiosk_out_longitude

            if (
                (out_lat or out_lon)
                and -90 <= out_lat <= 90
                and -180 <= out_lon <= 180
            ):
                attendance.kiosk_out_map_html = (
                    '<iframe '
                    'width="100%" height="160" '
                    'style="border:0; display:block;" '
                    'loading="lazy" '
                    'referrerpolicy="no-referrer-when-downgrade" '
                    'allowfullscreen '
                    'src="https://maps.google.com/maps?'
                    f'q={out_lat:.7f},{out_lon:.7f}&output=embed">'
                    '</iframe>'
                )


    # =========================================================
    # REQUEST METADATA
    # =========================================================

    @api.model
    def _kiosk_get_request_metadata(self):
        """Get browser and client IP from the current Odoo HTTP request."""
        try:
            http_request = request.httprequest
            user_agent = http_request.user_agent

            browser_name = user_agent.browser or "Unknown browser"
            browser_version = user_agent.version or ""
            platform = user_agent.platform or ""

            browser = f"{browser_name} {browser_version}".strip()

            if platform:
                browser = f"{browser} | {platform}"

            # Do not trust a client-supplied X-Forwarded-For header.
            # Configure Odoo proxy_mode and trusted reverse proxy correctly
            # if the server is behind a reverse proxy.
            ip_address = http_request.remote_addr or ""

            return {
                "browser": browser[:512],
                "ip": ip_address[:45],
            }

        except (RuntimeError, AttributeError):
            return {
                "browser": "Unavailable",
                "ip": "",
            }

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
        # VALIDATE PHOTO
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

        photo_base64 = base64.b64encode(photo)

        # -----------------------------------------------------
        # VALIDATE GPS VALUES
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
        # VALIDATE OFFICE RADIUS ON SERVER
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
        # SERVER REQUEST METADATA
        # -----------------------------------------------------

        metadata = self._kiosk_get_request_metadata()

        # -----------------------------------------------------
        # FIND EXISTING OPEN ATTENDANCE
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

                "kiosk_in_photo": photo_base64,
                "kiosk_in_latitude": latitude,
                "kiosk_in_longitude": longitude,
                "kiosk_in_accuracy": accuracy,

                "kiosk_in_browser": metadata["browser"],
                "kiosk_in_ip": metadata["ip"],
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

            "kiosk_out_photo": photo_base64,
            "kiosk_out_latitude": latitude,
            "kiosk_out_longitude": longitude,
            "kiosk_out_accuracy": accuracy,

            "kiosk_out_browser": metadata["browser"],
            "kiosk_out_ip": metadata["ip"],
        })

        return {
            "success": True,
            "action": "check_out",
            "attendance_id": open_attendance.id,
            "checked_in": False,
            "message": _("Check Out recorded successfully."),
        }
