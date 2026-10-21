from odoo import fields, models, _
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = "res.company"

    attendance_kiosk_office_latitude = fields.Float(string="Office Latitude", digits=(10, 7))
    attendance_kiosk_office_longitude = fields.Float(string="Office Longitude", digits=(10, 7))
    attendance_kiosk_office_radius = fields.Float(string="Allowed Radius (meters)", default=50.0)

    def write(self, vals):
        for company in self:
            lat = vals.get("attendance_kiosk_office_latitude", company.attendance_kiosk_office_latitude)
            lon = vals.get("attendance_kiosk_office_longitude", company.attendance_kiosk_office_longitude)
            radius = vals.get("attendance_kiosk_office_radius", company.attendance_kiosk_office_radius)
            if lat and not -90 <= lat <= 90:
                raise ValidationError(_("Latitude must be between -90 and 90."))
            if lon and not -180 <= lon <= 180:
                raise ValidationError(_("Longitude must be between -180 and 180."))
            if radius < 1 or radius > 5000:
                raise ValidationError(_("Radius must be between 1 and 5000 meters."))
        return super().write(vals)


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    attendance_kiosk_office_latitude = fields.Float(
        related="company_id.attendance_kiosk_office_latitude", readonly=False, digits=(10, 7))
    attendance_kiosk_office_longitude = fields.Float(
        related="company_id.attendance_kiosk_office_longitude", readonly=False, digits=(10, 7))
    attendance_kiosk_office_radius = fields.Float(
        related="company_id.attendance_kiosk_office_radius", readonly=False)
