import ckan.plugins as plugins
import ckan.plugins.toolkit as toolkit
# from ckanext.scheming.helpers import scheming_get_dataset_schema
import ckan.lib.helpers as h
from ckan.common import _
from flask import Blueprint, request, jsonify, redirect, send_file, make_response
from urllib import quote
from werkzeug.datastructures import FileStorage
import os
import uuid
import json
import datetime
import logging
from ckan.lib.plugins import DefaultTranslation

log = logging.getLogger()

try:
    from ckanext.xloader.interfaces import IXloader
except ImportError:
    IXloader = None


def file_uploader_ui():
    package_id = request.form['package_id']
    package_show = toolkit.get_action('package_show')
    # this ensures current user is authorized to view the package
    package = package_show(data_dict={'name_or_id': package_id})
    package_id = package['id']
    assert package
    files = request.files.values()
    assert len(files) == 1
    file_storage = files[0] # type: FileStorage
    file_uuid = str(uuid.uuid4())
    file_path = os.path.join(
        toolkit.config.get('ckan.storage_path'),
        toolkit.config.get('ckanext.file_uploader_ui_path', 'file_uploader_ui'),
        package_id)
    # Keep these logs appearing in production for the Jan 2020 West Africa meet
    log.info("Bulk uploading file to path: {}".format(file_path))

    try:
        os.makedirs(file_path)
    except OSError as e:
        # errno 17 is file already exists
        if e.errno != 17:
            raise

    
    file = os.path.join(file_path, file_storage.filename)
    file_storage.save(file)
    # with open(os.path.join(file_path, 'metadata'), 'w') as f:
        # json.dump({'name': file_storage.filename, 'status': 'pending'}, f)
    return jsonify({'files': [{'name': file_storage.filename, 'size':os.path.getsize(file)}]})

def file_uploader_finish(package_id, package_type=None, resource_type=None):
    package_show = toolkit.get_action('package_show')
    # this ensures current user is authorized to view the package
    package = package_show(data_dict={'name_or_id': package_id})
    assert package
    package_id = package['id']
    resource_create = toolkit.get_action('resource_create')
    package_path = os.path.join(
        toolkit.config.get('ckan.storage_path'),
        toolkit.config.get('ckanext.file_uploader_ui_path', 'file_uploader_ui'),
        package_id
    )
    file_metadatas = {}
    uploads = []
    for file_name in os.listdir(package_path):
        file_path = os.path.join(package_path, file_name)
        with open(file_path,'r') as f:
            file_upload_storage = FileStorage(f)
            data_dict = {
                'package_id': package_id,
                'name': file_name,
                'upload': file_upload_storage,
                'last_modified': datetime.datetime.utcnow() }
            data_dict = _merge_with_configured_defaults(data_dict)
            # data_dict = _merge_with_schema_default_values(
                # package_type,
                # resource_type,
                # data_dict)
            resource_create(data_dict=data_dict)
            uploads.append(file_name)
        os.remove(file_path)

    package_show = toolkit.get_action('package_show')
    package_update = toolkit.get_action('package_update')

    if uploads:
        h.flash_success(_('The following resources were created: {}').format(', '.join(uploads)))

    return toolkit.redirect_to(controller='package', action='resources', id=package_id)

def _merge_with_configured_defaults(data_dict):
    """
    Allow configurable default values for resource properties created through
    file uploader. These are configured through a json string in the config.
    """
    defaults = toolkit.config.get('ckanext.file_uploader_ui_defaults', "")
    if defaults:
        defaults = json.loads(defaults)
        for key, value in defaults.items():
            data_dict[key] = value
    return data_dict


# def _merge_with_schema_default_values(package_type, resource_type, data_dict):
    # """
    # This function merges the file uploader default resource with the default
    # values specified in the ckanext-schemining schema. It allows us to bulk
    # upload multiple copies ofa particular resource type e.g. multiple spectrum
    # files.
    # """
    # # If no package_type or resource_type we can't do this.
    # if not (package_type and resource_type):
        # return data_dict

    # schema = scheming_get_dataset_schema(package_type)
    # resource_schemas = schema.get("resource_schemas", {})
    # resource_schema = resource_schemas.get(resource_type, {})
    # file_name = data_dict['name']

    # # Step through each field and merge in the default value if it exits.
    # for field in resource_schema.get('resource_fields', []):
        # if field['field_name'] == 'restricted':
            # # TODO: Would be nice if restricted didn't need special treatment
            # data_dict["restricted_allowed_users"] = field.get('default_users', "")
            # data_dict["restricted_allowed_orgs"] = field.get('default_organizations', "")
        # value = field.get('default', field.get('field_value'))
        # if value:
            # data_dict[field['field_name']] = value

    # # Multiple resources with the same name is confusing, so merge in filename
    # data_dict['name'] = "{}: {}".format(
        # data_dict.get('name', ""),
        # file_name
    # )
    # return data_dict


class File_Uploader_UiPlugin(plugins.SingletonPlugin, DefaultTranslation):
    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.IBlueprint)
    plugins.implements(plugins.ITranslation)
    if IXloader:
        plugins.implements(IXloader)

    def update_config(self, config_):
        toolkit.add_template_directory(config_, 'templates')
        toolkit.add_public_directory(config_, 'public')
        toolkit.add_resource('fanstatic', 'file_uploader_ui')

    def i18n_domain(self):
        return 'ckanext-file_uploader_ui'

    def get_blueprint(self):
        blueprint = Blueprint(self.name, self.__module__)
        blueprint.template_folder = u'templates'
        blueprint.add_url_rule(u'/file_uploader_ui/upload',
                               u'file_uploader_ui_upload',
                               file_uploader_ui,
                               methods=['POST'])
        blueprint.add_url_rule(u'/file_uploader_ui/finish/<package_id>',
                               u'file_uploader_ui_finish',
                               file_uploader_finish,
                               methods=['GET'])
        blueprint.add_url_rule(u'/file_uploader_ui/finish/<package_id>/<package_type>/<resource_type>',
                               u'file_uploader_ui_finish',
                               file_uploader_finish,
                               methods=['GET'])
        # blueprint.add_url_rule(u'/file_uploader_ui/download/<package_id>/<file_id>',
                               # u'file_uploader_ui_download',
                               # file_uploader_download,
                               # methods=['GET'])
        return blueprint

    def modify_download_request(self, url, resource, api_key, headers):
        if 'file_uploader_ui' in url:
            headers['Authorization'] = api_key
        return url

    def can_upload(self, resource_id):
        return True

    def after_upload(self, context, resource_dict, dataset_dict):
        pass
