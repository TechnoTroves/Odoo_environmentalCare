from odoo import http
from odoo.http import request

class EnvEventWebsite(http.Controller):
    #1. List
    @http.route('/events', type='http', auth='user', website=True)
    def event_list(self, **kw):
        events = request.env['envcare.event'].sudo().search([])
        return request.render('environmental_care.event_list_template', {'events': events})

    #2. Detail
    @http.route('/event/<model("envcare.event"):event>', type='http', auth='user', website=True)
    def event_detail(self, event, **kw):
        #FIXME: this will change once the access user group is created
        can_edit = not request.env.user._is_public() and request.env.user.has_group('base.group_user')
        return request.render('environmental_care.event_detail_template', {
            'event': event,
            'can_edit': can_edit
        })
    
    #3. Form
    ## Edit
    @http.route('/event/edit/<model("envcare.event"):event>', type='http', auth='user', website=True)
    def event_edit_form(self, event, **kw):
        return request.render('environmental_care.event_form_template', {'event': event})

    ## Update
    @http.route('/event/update/<model("envcare.event"):event>', type='http', auth='user', website=True)
    def event_update_form(self, event, **post):
        event.sudo().write({
            'name': post.get('name'),
            # add other fields
        })
        return request.redirect(f'/event/{event.id}')