from flask import current_app, render_template, request, redirect, url_for, abort, session, g, jsonify, Blueprint
from flask_login import login_required, current_user

from core.repository import repos
from core.pagination import paginate
from core.models import Parser, Metric
from context import PARSERS_DB

from datetime import datetime, date
import logging


PARSER_FILE_EXTENSIONS = {'python': 'py'}

bp = Blueprint('parsers', __name__)

def setup(config=None):
    """Setup parsers blueprint with configuration."""
    return bp


@bp.route('/parsers')
@login_required
def listParsers():
    current_app.logger.debug("Route [parsers.listParsers] called (json=%s, page=%s)", request.args.get('json'), request.args.get('page'))
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 100, type=int)
    
    # Optional search filter by name
    name_filter = request.args.get('name', '')
    
    pagination = paginate(repos['Parser'], page=page, per_page=per_page)
    
    if request.args.get('json', 'false').lower() in ["1", "true"]:
        return jsonify(pagination.to_dict())
    
    return render_template(
        f"{g.get('language', {}).get('code', 'en')}/parsers/list.html",
        pagination=pagination
    )


@bp.route('/parser')
@login_required
def newParser():
    current_app.logger.debug("Route [parsers.newParser] serving new parser form")
    return render_template(
        f"{g.get('language', {}).get('code', 'en')}/parsers/new.html"
    )


@bp.route('/parser', methods=["POST"])
@login_required
def createParser():
    current_app.logger.debug("Route [parsers.createParser] creating parser")
    data = request.form.to_dict() if request.form else request.get_json()
    
    # Handle JSON fields - set to None if empty
    for field in ["config_schema"]:
        if data.get(field, "").strip() == "":
            data[field] = None
    
    parser = Parser(
        name=data.get('name'),
        version=data.get('version'),
        description=data.get('description'),
        language=data.get('language', 'python'),
        config_schema=data.get('config_schema'),
        active=data.get('active', 'on').lower() in ['on', '1', 'true'] if isinstance(data.get('active', 'on'), str) else bool(data.get('active')),
        created_at=datetime.utcnow()
    )
    repos['Parser'].create(parser)
    current_app.logger.info("Route [parsers.createParser] parser created (id=%s)", parser.id)
    return redirect(url_for("parsers.listParsers"))


@bp.route('/parser/<int:parser_id>')
@login_required
def viewParser(parser_id):
    current_app.logger.debug("Route [parsers.viewParser] called (parser_id=%s)", parser_id)
    parser = repos['Parser'].get(id=parser_id)
    if parser is None:
        current_app.logger.warning("Route [parsers.viewParser] parser not found (id=%s)", parser_id)
        return abort(404)

    code_filename = "_".join([parser.name.lower().replace(" ", "_"), parser.version.lower().replace('.', '_')])
    try:
        code = PARSERS_DB.read(code_filename)
    except Exception:
        current_app.logger.warning("Route [parsers.viewParser] parser source not found (file=%s)", code_filename)
        code = None

    return render_template(
        f"{g.get('language', {}).get('code', 'en')}/parsers/view.html",
        parser=parser, code=code, metrics=repos['Metric'].list()
    )



@bp.route('/parser/<int:parser_id>', methods=["PUT", "PATCH"])
@login_required
def editParser(parser_id):
    current_app.logger.debug("Route [parsers.editParser] called (parser_id=%s)", parser_id)
    parser = repos['Parser'].get(id=parser_id)
    if parser is None:
        current_app.logger.warning("Route [parsers.editParser] parser not found (id=%s)", parser_id)
        return abort(404)

    data = request.get_json() or request.form.to_dict()
    updatable = {'name', 'version', 'description', 'language', 'config_schema', 'active'}
    update_dict = {k: v for k, v in data.items() if k in updatable}
    
    # Handle boolean conversion for active field
    if 'active' in update_dict:
        update_dict['active'] = update_dict['active'].lower() in ['true', '1', 'on'] if isinstance(update_dict['active'], str) else bool(update_dict['active'])
    
    # Handle parser code file storage
    if data.get('code') is not None:
        code_filename = "_".join([parser.name.lower().replace(" ", "_"), parser.version.lower().replace('.', '_')])
        PARSERS_DB.write(code_filename, data['code'])
        # Also write with language-specific extension
        try:
            ext = PARSER_FILE_EXTENSIONS.get(parser.language.lower(), 'py')
            code_filename_with_suffix = f"{code_filename}.{ext}"
            PARSERS_DB.write(code_filename_with_suffix, data['code'])
        except Exception as e:
            current_app.logger.warning("Route [parsers.editParser] failed to write parser with extension (error=%s)", str(e))

    repos['Parser'].update(parser, **update_dict)
    current_app.logger.info("Route [parsers.editParser] parser updated (id=%s)", parser_id)
    return jsonify(status="updated", data=parser.to_dict())


@bp.route('/parser/<int:parser_id>', methods=["DELETE"])
@login_required
def deleteParser(parser_id):
    current_app.logger.debug("Route [parsers.deleteParser] called (parser_id=%s)", parser_id)
    parser = repos['Parser'].get(id=parser_id)
    if parser is None:
        current_app.logger.warning("Route [parsers.deleteParser] parser not found (id=%s)", parser_id)
        return abort(404)

    parser_dict = parser.to_dict()
    repos['Parser'].delete(parser)
    current_app.logger.info("Route [parsers.deleteParser] parser deleted (id=%s)", parser_id)
    return jsonify(status="deleted", data=parser_dict)