"""The server and main app for kilink."""

import json
import logging

from flask import (
    Flask,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
)
from sqlalchemy import create_engine

import backend
import loghelper

from config import config
from decorators import crossdomain

# set up flask
app = Flask(__name__)
app.config.from_object(__name__)
app.config["STATIC_URL"] = 'static'
app.config["STATIC_ROOT"] = 'static'

# logger
logger = logging.getLogger('kilink.kilink')


# accesory pages
@app.route('/about')
def about():
    """Show the about page."""
    return render_template('_about.html')


@app.route('/tools')
def tools():
    """Show the about page."""
    return render_template('_tools.html')


# views
@app.route('/')
def index():
    """The base page."""
    render_dict = {
        'value': '',
        'button_text': 'Create linkode',
        'kid_info': 'l/',
        'tree_info': json.dumps(False),
    }
    return render_template('_new.html', **render_dict)


@app.route('/l/', methods=['POST'])
def create():
    """Create a kilink."""
    content = request.form['content']
    text_type = request.form['text_type']
    logger.debug("Create start; type=%r size=%d", text_type, len(content))
    if text_type[:6] == "auto: ":
        text_type = text_type[6:]
    klnk = kilinkbackend.create_kilink(content, text_type)
    url = "/l/%s" % (klnk.kid,)
    logger.debug("Create done; kid=%s", klnk.kid)
    return redirect(url, code=303)


@app.route('/l/<kid>', methods=['POST'])
@app.route('/l/<kid>/<parent>', methods=['POST'])
def update(kid, parent=None):
    """Update a kilink."""
    content = request.form['content']
    text_type = request.form['text_type']
    logger.debug("Update start; kid=%r parent=%r type=%r size=%d",
                 kid, parent, text_type, len(content))
    if parent is None:
        root = kilinkbackend.get_root_node(kid)
        parent = root.revno

    klnk = kilinkbackend.update_kilink(kid, parent, content, text_type)
    new_url = "/l/%s/%s" % (kid, klnk.revno)
    logger.debug("Update done; kid=%r revno=%r", klnk.kid, klnk.revno)
    return redirect(new_url, code=303)


@app.route('/l/<kid>')
@app.route('/l/<kid>/<revno>')
def show(kid, revno=None):
    """Show the kilink content"""
    # get the content
    logger.debug("Show start; kid=%r revno=%r", kid, revno)
    if revno is None:
        klnk = kilinkbackend.get_root_node(kid)
        revno = klnk.revno
    else:
        klnk = kilinkbackend.get_kilink(kid, revno)
    content = klnk.content
    text_type = klnk.text_type

    # node list
    node_list = []
    for treenode in kilinkbackend.get_kilink_tree(kid):
        url = "/l/%s/%s" % (kid, treenode.revno)
        parent = treenode.parent
        node_list.append({
            'order': treenode.order,
            'parent': parent,
            'revno': treenode.revno,
            'url': url,
            'timestamp': str(treenode.timestamp),
            'selected': treenode.revno == revno,
        })

    tree = {}
    build_tree(tree, {}, node_list)

    render_dict = {
        'value': content,
        'button_text': 'Save new version',
        'kid_info': "l/%s/%s" % (kid, revno),
        'tree_info': json.dumps(tree) if tree != {} else False,
        'current_revno': revno,
        'text_type': text_type,
    }
    logger.debug("Show done; quantity=%d", len(node_list))
    return render_template('_new.html', **render_dict)


def build_tree(tree, parent, nodes):
    """ Build tree for 3djs """

    children = [
        n for n in nodes
        if n.get('parent', None) == parent.get('revno', None)
    ]

    for child in children:
        if tree == {}:
            tree['contents'] = []
            tree['order'] = child['order']
            tree['revno'] = child['revno']
            tree['parent'] = child['parent']
            tree['url'] = child['url']
            tree['timestamp'] = child['timestamp']
            tree['selected'] = child['selected']
            new_child = tree
        else:
            new_child = {
                'contents': [],
                'order': child['order'],
                'revno': child['revno'],
                'parent': child['parent'],
                'url': child['url'],
                'timestamp': child['timestamp'],
                'selected': child['selected'],
            }
            tree['contents'].append(new_child)
        build_tree(new_child, child, nodes)


#API
@app.route('/api/1/linkodes', methods=['POST'])
@crossdomain(origin='*')
def api_create():
    """Create a kilink."""
    content = request.form['content']
    text_type = request.form.get('text_type', "")
    logger.debug("API create start; type=%r size=%d", text_type, len(content))
    klnk = kilinkbackend.create_kilink(content, text_type)
    ret_json = jsonify(linkode_id=klnk.kid, revno=klnk.revno)
    response = make_response(ret_json)
    response.headers['Location'] = 'http://%s/%s/%s' % (
        config["server_host"], klnk.kid, klnk.revno)
    logger.debug("API create done; kid=%s", klnk.kid)
    return response, 201


@app.route('/api/1/linkodes/<kid>', methods=['POST'])
@crossdomain(origin='*')
def api_update(kid):
    """Update a kilink."""
    content = request.form['content']
    parent = request.form['parent']
    text_type = request.form['text_type']
    logger.debug("API update start; kid=%r parent=%r type=%r size=%d",
                 kid, parent, text_type, len(content))
    try:
        klnk = kilinkbackend.update_kilink(kid, parent, content, text_type)
    except backend.KilinkNotFoundError:
        logger.debug("API update done; kid %r not found", kid)
        response = make_response()
        return response, 404

    logger.debug("API update done; kid=%r revno=%r", klnk.kid, klnk.revno)
    ret_json = jsonify(revno=klnk.revno)
    response = make_response(ret_json)
    response.headers['Location'] = 'http://%s/%s/%s' % (
        config["server_host"], klnk.kid, klnk.revno)
    return response, 201


@app.route('/api/1/linkodes/<kid>/<revno>', methods=['GET'])
@crossdomain(origin='*')
def api_get(kid, revno):
    """Get the kilink and revno content"""
    logger.debug("API get; kid=%r revno=%r", kid, revno)
    try:
        klnk = kilinkbackend.get_kilink(kid, revno)
    except backend.KilinkNotFoundError:
        logger.debug("API get; kid %r not found", kid)
        response = make_response()
        return response, 404

    logger.debug("API get done; type=%r size=%d",
                 klnk.text_type, len(klnk.content))
    ret_json = jsonify(content=klnk.content, text_type=klnk.text_type)
    return ret_json


if __name__ == "__main__":
    # load config
    config.load_file("configs/development.yaml")

    # log setup
    loghelper.setup_logging(config['log_directory'], verbose=True)

    # set up the backend
    engine = create_engine(config["db_engine"])
    kilinkbackend = backend.KilinkBackend(engine)
    app.run(debug=True, host='0.0.0.0')
