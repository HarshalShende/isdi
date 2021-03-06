from flask import (
    Flask, render_template, request, redirect, g, jsonify,
    url_for, session
)
import os
import json
import config
from time import strftime
from datetime import datetime, timedelta
import logging
from logging.handlers import RotatingFileHandler
from phone_scanner import AndroidScan, IosScan, TestScan
# import traceback
from privacy_scan_android import do_privacy_check
from db import (
    create_scan, save_note, update_appinfo,
    create_report, new_client_id, init_db, create_mult_appinfo,
    get_client_devices_from_db, get_device_from_db, update_mul_appinfo,
    get_serial_from_db, get_scan_res_from_db, get_app_info_from_db
)

#from flask_wtf import Form
#from sqlalchemy.orm import validates
from flask_migrate import Migrate
from flask_sqlalchemy import Model, SQLAlchemy
import json
import config
from time import strftime
from wtforms_alchemy import ModelForm
from sqlalchemy import *
from wtforms.validators import Email, InputRequired
from wtforms.fields import SelectMultipleField
from wtforms.widgets import CheckboxInput, ListWidget

app = Flask(__name__, static_folder='webstatic')
app.config['SQLALCHEMY_DATABASE_URI'] = config.SQL_DB_PATH
app.config['SQLALCHEMY_ECHO'] = True
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = config.FLASK_SECRET # doesn't seem to be necessary
app.config['SECRET_KEY'] = config.FLASK_SECRET # doesn't seem to be necessary
app.config['SESSION_TYPE'] = 'filesystem'
sa=SQLAlchemy(app)
Migrate(app, sa)
# sa.create_all() # run in init_db()

# If changes are made to this model, please run 
# `flask db migrate` and then delete the drops to other tables from the upgrade() method in 
# migrations/versions/<version>.py
# before running `flask db upgrade` and re-launching the server.
# if the migrations folder isn't present, run `flask db init` first.
# _order in ClientForm should be modified .
class Client(sa.Model):
    __tablename__ = 'clients_notes'
    _d = {'default': '', 'server_default': ''} # makes migrations smooth
    _d0 = {'default': '0', 'server_default': '0'}
    _lr = lambda label,req: {'label':label+'*' if req=='r' else label,'validators':InputRequired() if req=='r' else ''}
    id = sa.Column(sa.Integer, primary_key=True)
    created_at = sa.Column(
        sa.DateTime,
        #default=datetime.now()
        # TODO: timestamp off by 4 hours? investigate.
        default=sa.func.current_timestamp(),
        #server_default=sa.func.current_timestamp() 
        #server_default=str(datetime.now()),
    )

    # TODO: link to session ClientID for scans, with foreignkey? across different db?
    # try using fieldstudy.db, creating table not dropping existing things. use ~test.
    clientid = sa.Column(sa.String(100), nullable=False, **_d)

    consultant_initials = sa.Column(sa.String(100), nullable=False,
            info=_lr('Consultant Names (separate with commas)','r'), **_d)

    fjc = sa.Column(sa.Enum('', 'Brooklyn', 'Queens', 'The Bronx', 'Manhattan', 'Staten Island'),
            nullable=False, info=_lr('FJC', 'r'), **_d)

    preferred_language = sa.Column(sa.String(100), nullable=False,
            info=_lr('Preferred language','r'), default='English', server_default='English')

    referring_professional = sa.Column(sa.String(100), nullable=False,
            info=_lr('Name of Referring Professional', 'r'), **_d)

    referring_professional_email = sa.Column(sa.String(255), nullable=True,
            info={'label': 'Email of Referring Professional (Optional)', 'validators':Email()})

    referring_professional_phone = sa.Column(sa.String(50), nullable=True,
            info={'label': 'Phone number of Referring Professional (Optional)'})

    caseworker_present = sa.Column(sa.Enum('', 'For entire consult', 'For part of the consult', 'No'),
            nullable=False, info=_lr('Caseworker present', 'r'), **_d)

    caseworker_present_safety_planning = sa.Column(sa.Enum('', 'Yes', 'No'),
            nullable=False, info=_lr('Caseworker present for safety planning', 'r'), **_d)

    caseworker_recorded = sa.Column(sa.Enum('', 'Yes', 'No'),
            nullable=False, info=_lr('If caseworker present, permission to audio-record them', 'r'), **_d)

    recorded = sa.Column(sa.Enum('', 'Yes', 'No'),
            nullable=False, info=_lr('Permission to audio-record clinic', 'r'), **_d)

    chief_concerns = sa.Column(sa.String(400), nullable=False,
            info=_lr('Chief concerns', 'r'), **_d)

    chief_concerns_other = sa.Column(sa.Text, nullable=False,
            info=_lr('Chief concerns if not listed above (Optional)', ''), **_d)

    android_phones = sa.Column(sa.Integer, nullable=False, 
            info=_lr('# of Android phones brought in','r'), **_d0)

    android_tablets = sa.Column(sa.Integer, nullable=False, 
            info=_lr('# of Android tablets brought in','r'), **_d0)

    iphone_devices = sa.Column(sa.Integer, nullable=False, 
            info=_lr('# of iPhones brought in','r'), **_d0)

    ipad_devices = sa.Column(sa.Integer, nullable=False, 
            info=_lr('# of iPads brought in','r'), **_d0)

    macbook_devices = sa.Column(sa.Integer, nullable=False, 
            info=_lr('# of MacBooks brought in','r'), **_d0)

    windows_devices = sa.Column(sa.Integer, nullable=False, 
            info=_lr('# of Windows laptops brought in','r'), **_d0)

    echo_devices = sa.Column(sa.Integer, nullable=False, 
            info=_lr('# of Amazon Echoes brought in','r'), **_d0)

    other_devices = sa.Column(sa.String(400), nullable=True,
            info=_lr('Other devices brought in if not listed above (Optional)', ''), **_d)

    # consider adding checkboxes for this
    checkups = sa.Column(sa.String(400), nullable=True,
            info=_lr('List apps/accounts manually checked (Optional)', ''), **_d)

    checkups_other = sa.Column(sa.String(400), nullable=True,
            info=_lr('Other apps/accounts manually checked (Optional)', ''), **_d)

    vulnerabilities = sa.Column(sa.String(600), nullable=False,
            info=_lr('Vulnerabilities discovered', 'r'), **_d)

    vulnerabilities_trusted_devices = sa.Column(sa.Text, nullable=True,
            info=_lr('List accounts with unknown trusted devices if discovered (Optional)', ''), **_d)

    vulnerabilities_other = sa.Column(sa.Text, nullable=True,
            info=_lr('Other vulnerabilities discovered (Optional)', ''), **_d)

    safety_planning_onsite = sa.Column(sa.Enum('', 'Yes', 'No', 'Not applicable'),
            nullable=False, info=_lr('Safety planning conducted onsite', 'r'), **_d)

    changes_made_onsite = sa.Column(sa.Text, nullable=True,
            info=_lr('Changes made onsite (Optional)', ''), **_d)

    unresolved_issues = sa.Column(sa.Text, nullable=True,
            info=_lr('Unresolved issues (Optional)', ''), **_d)

    follow_ups_todo = sa.Column(sa.Text, nullable=True,
            info=_lr('Follow-ups To-do (Optional)', ''), **_d)

    general_notes = sa.Column(sa.Text, nullable=True,
            info=_lr('General notes (Optional)', ''), **_d)

    case_summary = sa.Column(sa.Text, nullable=True,
            info=_lr('Case Summary (Can fill out after consult, see "Edit previous forms")', ''), **_d)

    # way to edit data/add case summaries afterwards? Or keep text files.

    def __repr__(self):
        return 'client seen on {}'.format(self.created_at)

from wtforms import TextAreaField

class ClientForm(ModelForm): 
    class Meta:
        model = Client

    chief_concerns = SelectMultipleField('Chief concerns*', choices=[
        ('spyware','Worried about spyware/tracking'),
        ('hacked','Abuser hacked accounts or knows secrets'),
        ('location','Worried abuser was tracking their location'),
        ('glitchy','Phone is glitchy'),
        ('unknown_calls','Abuser calls/texts from unknown numbers'),
        ('social_media','Social media concerns (e.g., fake accounts, harassment)'),
        ('child_devices','Concerns about child device(s), e.g., unknown apps'),
        ('financial_concerns','Financial concerns, e.g., fraud, money missing from bank account'),
        ('curious','Curious and want to learn about privacy'),
        ('sms','SMS texts'),
        ('other','Other chief concern (write in next question)')],
        coerce = str, option_widget = CheckboxInput(), widget = ListWidget(prefix_label=False))

    checkups = SelectMultipleField('List apps/accounts manually checked (Optional)', choices=[
        ('facebook','Facebook'),
        ('instagram','Instagram'),
        ('snapchat','SnapChat'),
        ('google','Google (including GMail)'),
        ('icloud','iCloud'),
        ('whatsapp','WhatsApp'),
        ('other','Other apps/accounts (write in next question)')],
        coerce = str, option_widget = CheckboxInput(), widget = ListWidget(prefix_label=False))

    vulnerabilities = SelectMultipleField('Vulnerabilities discovered*', choices=[
        ('none','None'),
        ('shared plan','Shared plan / abuser pays for plan'),
        ('password:observed compromise','Observed compromise (e.g., client reports abuser shoulder-surfed, or told them password)'),
        ('password:guessable','Surfaced guessable passwords'),
        ('cloud:stored passwords','Stored passwords in app that is synced to cloud (e.g., passwords written in Notes and backed up)'),
        ('cloud:passwords synced/password manager','Password syncing (e.g., iCloud Keychain)'),
        ('unknown trusted device','Found an account with an active login from a device not under client\'s control; trusted device'),
        ('ISDi:found dual-use apps/spyware','ISDi found dual-use apps/spyware'),
        ('ISDi:false positive','ISDi false positive as confirmed by client'),
        ('browser extension','Browser extension potential spyware'),
        ('desktop potential spyware','Desktop application potential spyware')
        ],
        coerce = str, option_widget = CheckboxInput(), widget = ListWidget(prefix_label=False))

    __order = ('fjc','consultant_initials','preferred_language','referring_professional','referring_professional_email',
            'referring_professional_phone', 'caseworker_present','caseworker_present_safety_planning',
            'recorded','caseworker_recorded','chief_concerns','chief_concerns_other','android_phones','android_tablets',
            'iphone_devices','ipad_devices','macbook_devices','windows_devices','echo_devices',
            'other_devices','checkups','checkups_other','vulnerabilities','vulnerabilities_trusted_devices',
            'vulnerabilities_other','safety_planning_onsite','changes_made_onsite',
            'unresolved_issues','follow_ups_todo','general_notes', 'case_summary')

    chief_concerns_other = TextAreaField('Chief concerns if not listed above (Optional)', render_kw={"rows": 5, "cols": 70})
    vulnerabilities_trusted_devices = TextAreaField('List accounts with unknown trusted devices if discovered (Optional)', render_kw={"rows": 5, "cols": 70})
    vulnerabilities_other = TextAreaField('Other vulnerabilities discovered (Optional)', render_kw={"rows": 5, "cols": 70})
    changes_made_onsite = TextAreaField('Changes made onsite (Optional)', render_kw={"rows": 5, "cols": 70})
    unresolved_issues = TextAreaField('Unresolved issues (Optional)', render_kw={"rows": 5, "cols": 70})
    follow_ups_todo = TextAreaField('Follow-ups To-do (Optional)', render_kw={"rows": 5, "cols": 70})
    general_notes = TextAreaField('General notes (Optional)', render_kw={"rows": 10, "cols": 70})
    case_summary = TextAreaField('Case Summary (Can fill out after consult, see "Edit previous forms")', render_kw={"rows": 10, "cols": 70})


    def __iter__(self): # https://stackoverflow.com/a/25323199
        fields = list(super(ClientForm, self).__iter__())
        get_field = lambda field_id: next((fld for fld in fields if fld.id == field_id))
        return (get_field(field_id) for field_id in self.__order)

# app.config['STATIC_FOLDER'] = 'webstatic'
android = AndroidScan()
ios = IosScan()
test = TestScan()


def get_device(k):
    return {
        'android': android,
        'ios': ios,
        'test': test
    }.get(k)


@app.before_request
def make_session_permanent():
    session.permanent = True
    # expires at midnight of new day
    app.permanent_session_lifetime = \
            (datetime.now() + timedelta(days=1)).replace(hour=0, minute=0, second=0) - datetime.now()
    #app.permanent_session_lifetime = timedelta(seconds=1)

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


@app.route("/", methods=['GET'])
def index():
    #clientid = request.form.get('clientid', request.args.get('clientid'))
    #if not clientid: # if not coming from notes

    newid = request.args.get('newid')
    # if it's a new day (see app.permenant_session_lifetime), 
    # or the client devices are all scanned (newid),
    # ask the DB for a new client ID (additional checks in DB).
    if 'clientid' not in session or (newid is not None):
        session['clientid']=new_client_id()

    return render_template(
        'main.html',
        title=config.TITLE,
        device_primary_user=config.DEVICE_PRIMARY_USER,
        task='home',
        devices={
            'Android': android.devices(),
            'iOS': ios.devices(),
            'Test': test.devices()
        },
        apps={},
        clientid=session['clientid'],
        currently_scanned=get_client_devices_from_db(session['clientid'])
    )


@app.route('/form/', methods=['GET', 'POST'])
def client_forms():
    if 'clientid' not in session:
        return redirect(url_for('index'))

    prev_submitted = Client.query.filter_by(clientid=session['clientid']).first()
    if prev_submitted:
        return redirect(url_for('edit_forms'))

    # retrieve form defaults from db schema
    client = Client()
    form = ClientForm(request.form)

    if request.method == 'POST':
        try:
            if form.validate():
                print('VALIDATED')
                # convert checkbox lists to json-friendly strings
                for field in form:
                    if field.type == 'SelectMultipleField':
                        field.data = json.dumps(field.data)
                form.populate_obj(client)
                client.clientid = session['clientid']
                sa.session.add(client)
                sa.session.commit()
                return render_template('main.html', task="form", formdone='yes', title=config.TITLE)
        except Exception as e:
            print('NOT VALIDATED')
            print(e)
            sa.session.rollback()

    #clients_list = Client.query.all()
    return render_template('main.html', task="form", form=form, title=config.TITLE, clientid=session['clientid'])

@app.route('/form/edit/', methods=['GET', 'POST'])
def edit_forms():
    if request.method == 'POST':
        clientnote = request.form.get('clientnote', request.args.get('clientnote'))

        if clientnote: # if requesting a form to edit
            session['form_edit_pk'] = clientnote # set session cookie
            form_obj = Client.query.get(clientnote)
            form = ClientForm(obj=form_obj)
            for field in form:
                if field.type == 'SelectMultipleField':
                    field.data = json.loads(''.join(field.data))
            return render_template('main.html', task="form",form=form, title=config.TITLE, clientid=form_obj.clientid)
        else: # if edits were submitted
            form_obj = Client.query.get(session['form_edit_pk'])
            cid = form_obj.clientid # preserve before populate_obj
            form = ClientForm(request.form)
            if form.validate():
                print('VALIDATED')
                # convert checkbox lists to json-friendly strings
                for field in form:
                    if field.type == 'SelectMultipleField':
                        field.data = json.dumps(field.data)
            form.populate_obj(form_obj)
            form_obj.clientid = cid
            sa.session.commit()
            return render_template('main.html', task="form", formdone='yes', title=config.TITLE)

    clients = Client.query.all()
    return render_template('main.html', clients=clients, task="formedit", title=config.TITLE)

@app.route('/details/app/<device>', methods=['GET'])
def app_details(device):
    sc = get_device(device)
    appid = request.args.get('appId')
    ser = request.args.get('serial')
    d, info = sc.app_details(ser, appid)
    d = d.fillna('')
    d = d.to_dict(orient='index').get(0, {})
    d['appId'] = appid

    # detect apple and put the key into d.permissions
    # if "Ios" in str(type(sc)):
    #    print("apple iphone")
    # else:
    #    print(type(sc))

    print(d.keys())
    return render_template(
        'main.html', task="app",
        title=config.TITLE,
        device_primary_user=config.DEVICE_PRIMARY_USER,
        app=d,
        info=info,
        device=device
    )


@app.route('/instruction', methods=['GET'])
def instruction():
    return render_template('main.html', task="instruction",
                           device_primary_user=config.DEVICE_PRIMARY_USER,
                           title=config.TITLE)


@app.route('/kill', methods=['POST', 'GET'])
def killme():
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        raise RuntimeError('Not running with the Werkzeug Server')
    func()
    return ("The app has been closed!")


def is_success(b, msg_succ="", msg_err=""):
    if b:
        return msg_succ if msg_succ else "Success!", 200
    else:
        return msg_err if msg_err else "Failed", 401


def first_element_or_none(l):
    if l and len(l) > 0:
        return l[0]


@app.route("/privacy", methods=['GET'])
def privacy():
    """
    TODO: Privacy scan. Think how should it flow.
    Privacy is a seperate page.
    """
    return render_template(
        'main.html', task="privacy",
        device_primary_user=config.DEVICE_PRIMARY_USER,
        title=config.TITLE
    )


@app.route("/privacy/<device>/<cmd>", methods=['GET'])
def privacy_scan(device, cmd):
    sc = get_device(device)
    res = do_privacy_check(sc.serialno, cmd)
    return res


@app.route("/view_results", methods=['POST', 'GET'])
def view_results():
    print("WORK IN PROGRESS")
    #clientid = request.form.get('clientid', request.args.get('clientid'))
    # hmac'ed serial of results we want to view
    scan_res_pk = request.form.get('scan_res', request.args.get('scan_res'))
    print(get_scan_res_from_db(scan_res_pk))
    print(get_app_info_from_db(scan_res_pk)[0].keys())

    # TODO: maybe unneccessary, but likely nice for returning without
    # re-drawing screen.
    last_serial = request.form.get(
        'last_serial', request.args.get('last_serial'))
    '''
    template_d = dict(
        task="home",
        title=config.TITLE,
        device=device,
        device_primary_user=config.DEVICE_PRIMARY_USER,   # TODO: Why is this sent
        device_primary_user_sel=device_primary_user,
        apps={},
        currently_scanned=currently_scanned,
        clientid=session['clientid']
    )
    
    apps = sc.find_spyapps(serialno=ser).fillna('').to_dict(orient='index')

    
    template_d.update(dict(
          isrooted=(
              "<strong class='text-danger'>Yes.</strong> Reason(s): {}"
              .format(rooted_reason) if rooted
              else "Don't know" if rooted is None
              else "No"
          ),
          device_name=device_name_print,
          apps=apps,
          scanid=scanid,
          sysapps=set(),  # sc.get_system_apps(serialno=ser)),
          serial=ser,
          # TODO: make this a map of model:link to display scan results for that
          # scan.
          error=config.error()
  ))
  '''


    if scan_res_pk == last_serial:
        print('Should return same template as before.')
        print("scan_res:  {}".format(scan_res_pk))
        print("last_serial: {}".format(last_serial))
    else:
        print('Should return results of scan_res.')
        print("scan_res: {}".format(scan_res_pk))
        print("last_serial: {}".format(last_serial))
    return redirect(url_for('index'))


@app.route("/scan", methods=['POST', 'GET'])
def scan():
    """
    Needs three attribute for a device
    :param device: "android" or "ios" or test
    :return: a flask view template
    """
    #clientid = request.form.get('clientid', request.args.get('clientid'))
    if 'clientid' not in session:
        return redirect(url_for('index'))

    device_primary_user = request.form.get(
        'device_primary_user',
        request.args.get('device_primary_user'))
    device = request.form.get('device', request.args.get('device'))
    action = request.form.get('action', request.args.get('action'))
    device_owner = request.form.get(
        'device_owner', request.args.get('device_owner'))

    currently_scanned = get_client_devices_from_db(session['clientid'])
    template_d = dict(
        task="home",
        title=config.TITLE,
        device=device,
        device_primary_user=config.DEVICE_PRIMARY_USER,   # TODO: Why is this sent
        device_primary_user_sel=device_primary_user,
        apps={},
        currently_scanned=currently_scanned,
        clientid=session['clientid']
    )
    # lookup devices scanned so far here. need to add this by model rather
    # than by serial.
    print('CURRENTLY SCANNED: {}'.format(currently_scanned))
    print('DEVICE OWNER IS: {}'.format(device_owner))
    print('PRIMARY USER IS: {}'.format(device_primary_user))
    print('-' * 80)
    print('CLIENT ID IS: {}'.format(session['clientid']))
    print('-' * 80)
    print("--> Action = ", action)

    sc = get_device(device)
    if not sc:
        template_d["error"] = "Please choose one device to scan."
        return render_template("main.html", **template_d), 201
    if not device_owner:
        template_d["error"] = "Please give the device a nickname."
        return render_template("main.html", **template_d), 201

    ser = sc.devices()

    print("Devices: {}".format(ser))
    if not ser:
        # FIXME: add pkexec scripts/ios_mount_linux.sh workflow for iOS if
        # needed.
        error = "<b>A device wasn't detected. Please follow the "\
            "<a href='/instruction' target='_blank' rel='noopener'>"\
            "setup instructions here.</a></b>"
        template_d["error"] = error
        return render_template("main.html", **template_d), 201

    ser = first_element_or_none(ser)
    # clientid = new_client_id()
    print(">>>scanning_device", device, ser, "<<<<<")

    if device == "ios":
        error = "If an iPhone is connected, open iTunes, click through the "\
                "connection dialog and wait for the \"Trust this computer\" "\
                "prompt to pop up in the iPhone, and then scan again."
    else:
        error = "If an Android device is connected, disconnect and reconnect "\
                "the device, make sure developer options is activated and USB "\
                "debugging is turned on on the device, and then scan again."
    error += "{} <b>Please follow the <a href='/instruction' target='_blank'"\
             " rel='noopener'>setup instructions here,</a> if needed.</b>"
    if device == 'ios':
        # go through pairing process and do not scan until it is successful.
        isconnected, reason = sc.setup()
        template_d["error"] = error.format(reason)
        template_d["currently_scanned"] = currently_scanned
        if not isconnected:
            return render_template("main.html", **template_d), 201

    # TODO: model for 'devices scanned so far:' device_name_map['model']
    # and save it to scan_res along with device_primary_user.
    device_name_print, device_name_map = sc.device_info(serial=ser)

    # Finds all the apps in the device
    # @apps have appid, title, flags, TODO: add icon
    apps = sc.find_spyapps(serialno=ser).fillna('').to_dict(orient='index')
    if len(apps) <= 0:
        print("The scanning failed for some reason.")
        error = "The scanning failed. This could be due to many reasons. Try"\
            " rerunning the scan from the beginning. If the problem persists,"\
            " please report it in the file. <code>report_failed.md</code> in the<code>"\
            "phone_scanner/</code> directory. Checn the phone manually. Sorry for"\
            " the inconvenience."
        template_d["error"] = error
        return render_template("main.html", **template_d), 201

    scan_d = {
        'clientid': session['clientid'],
        'serial': config.hmac_serial(ser),
        'device': device,
        'device_model': device_name_map.get('model', '<Unknown>').strip(),
        'device_version': device_name_map.get('version', '<Unknown>').strip(),
        'device_primary_user': device_owner,
    }

    if device == 'ios':
        scan_d['device_manufacturer'] = 'Apple'
        scan_d['last_full_charge'] = 'unknown'
    else:
        scan_d['device_manufacturer'] = device_name_map.get(
            'brand', "<Unknown>").strip()
        scan_d['last_full_charge'] = device_name_map.get(
            'last_full_charge', "<Unknown>")

    rooted, rooted_reason = sc.isrooted(ser)
    scan_d['is_rooted'] = rooted
    scan_d['rooted_reasons'] = json.dumps(rooted_reason)

    # TODO: here, adjust client session.
    scanid = create_scan(scan_d)

    if device == 'ios':
        pii_fpath = sc.dump_path(ser, 'Device_Info')
        print('Revelant info saved to db. Deleting {} now.'.format(pii_fpath))
        cmd = os.unlink(pii_fpath)
        # s = catch_err(run_command(cmd), msg="Delete pii failed", cmd=cmd)
        print('iOS PII deleted.')

    print("Creating appinfo...")
    create_mult_appinfo([(scanid, appid, json.dumps(
        info['flags']), '', '<new>') for appid, info in apps.items()])

    currently_scanned = get_client_devices_from_db(session['clientid'])
    template_d.update(dict(
        isrooted=(
            "<strong class='text-info'>Maybe (this is possibly just a bug with our scanning tool).</strong> Reason(s): {}"
            .format(rooted_reason) if rooted
            else "Don't know" if rooted is None 
            else "No"
        ),
        device_name=device_name_print,
        apps=apps,
        scanid=scanid,
        sysapps=set(),  # sc.get_system_apps(serialno=ser)),
        serial=ser,
        currently_scanned=currently_scanned,
        # TODO: make this a map of model:link to display scan results for that
        # scan.
        error=config.error()
    ))
    return render_template("main.html", **template_d), 200
    
##############  RECORD DATA PART  ###############################


@app.route("/delete/app/<scanid>", methods=["POST", "GET"])
def delete_app(scanid):
    device = get_device_from_db(scanid)
    serial = get_serial_from_db(scanid)
    sc = get_device(device)
    appid = request.form.get('appid')
    remark = request.form.get('remark')
    action = "delete"
    # TODO: Record the uninstall and note
    r = sc.uninstall(serial=serial, appid=appid)
    if r:
        r = update_appinfo(
            scanid=scanid, appid=appid, remark=remark, action=action
        )
        print("Update appinfo failed! r={}".format(r))
    else:
        print("Uninstall failed. r={}".format(r))
    return is_success(r, "Success!", config.error())


# @app.route('/save/appnote/<device>', methods=["POST"])
# def save_app_note(device):
#     sc = get_device(device)
#     serial = request.form.get('serial')
#     appId = request.form.get('appId')
#     note = request.form.get('note')
# return is_success(sc.save('appinfo', serial=serial, appId=appId,
# note=note))

@app.route('/saveapps/<scanid>', methods=["POST"])
def record_applist(scanid):
    device = get_device_from_db(scanid)
    sc = get_device(device)
    d = request.form
    update_mul_appinfo([(remark, scanid, appid)
                        for appid, remark in d.items()])
    return "Success", 200


@app.route('/savescan/<scanid>', methods=["POST"])
def record_scanres(scanid):
    device = get_device_from_db(scanid)
    sc = get_device(device)
    note = request.form.get('notes')
    r = save_note(scanid, note)
    create_report(session['clientid'])
    #create_report(request.form.get('clientid'))
    return is_success(
        r,
        "Success!",
        "Could not save the form. See logs in the terminal.")


################# For logging ##############################################
@app.route("/error")
def get_nothing():
    """ Route for intentional error. """
    return "foobar"  # intentional non-existent variable


@app.after_request
def after_request(response):
    """ Logging after every request. """
    # This avoids the duplication of registry in the log,
    # since that 500 is already logged via @app.errorhandler.
    if response.status_code != 500:
        ts = strftime('[%Y-%b-%d %H:%M]')
        logger.error('%s %s %s %s %s %s',
                     ts,
                     request.remote_addr,
                     request.method,
                     request.scheme,
                     request.full_path,
                     response.status)
    return response

# @app.errorhandler(Exception)
# def exceptions(e):
#     """ Logging after every Exception. """
#     ts = strftime('[%Y-%b-%d %H:%M]')
#     tb = traceback.format_exc()
#     logger.error('%s %s %s %s %s 5xx INTERNAL SERVER ERROR\n%s',
#                   ts,
#                   request.remote_addr,
#                   request.method,
#                   request.scheme,
#                   request.full_path,
#                   tb)
#     print(e, file=sys.stderr)
#     return "Internal server error", 500


if __name__ == "__main__":
    import sys
    if 'TEST' in sys.argv[1:] or 'test' in sys.argv[1:]:
        print("Running in test mode.")
        config.set_test_mode(True)
        print("Checking mode = {}\nApp flags: {}\nSQL_DB: {}"
              .format(config.TEST, config.APP_FLAGS_FILE,
                      config.SQL_DB_PATH))
    print("TEST={}".format(config.TEST))
    init_db(app, sa, force=config.TEST)
    handler = RotatingFileHandler('logs/app.log', maxBytes=100000,
                                  backupCount=30)
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.ERROR)
    logger.addHandler(handler)
    port = 5000 if not config.TEST else 5002
    app.run(host="0.0.0.0", port=port, debug=config.DEBUG)
