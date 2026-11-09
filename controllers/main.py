from odoo import http
from odoo.http import request


class EnvEventWebsite(http.Controller):
    # No sudo() here: ACLs and record rules decide what the user sees/edits.

    #1. List
    @http.route('/events', type='http', auth='user', website=True)
    def event_list(self, **kw):
        events = request.env['envcare.event'].search([])
        return request.render('environmental_care.event_list_template', {'events': events})

    #2. Detail
    @http.route('/event/<model("envcare.event"):event>', type='http', auth='user', website=True)
    def event_detail(self, event, **kw):
        return request.render('environmental_care.event_detail_template', {
            'event': event,
            'can_edit': event.can_edit,
        })

    #3. Form
    ## Edit
    @http.route('/event/edit/<model("envcare.event"):event>', type='http', auth='user', website=True)
    def event_edit_form(self, event, **kw):
        if not event.can_edit:
            return request.redirect(f'/event/{event.id}')
        return request.render('environmental_care.event_form_template', {'event': event})

    ## Update
    @http.route('/event/update/<model("envcare.event"):event>', type='http', auth='user', website=True, methods=['POST'])
    def event_update_form(self, event, **post):
        if not event.can_edit:
            return request.redirect(f'/event/{event.id}')
        # write() without sudo -> record rule re-checks on the server
        event.write({
            'name': post.get('name'),
            # add other fields
        })
        return request.redirect(f'/event/{event.id}')