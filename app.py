import yaml
import os
import json
import requests
from urllib.parse import urlencode
from flask import Flask, render_template, request, session, redirect, url_for, g, flash, jsonify
from flask_babel import Babel, gettext
from wikidata import query_quantidade, query_by_type, query_metadata_of_work, query_next_qid, api_category_members
from oauth_wiki import get_username, get_token, upload_file
from requests_oauthlib import OAuth1Session
from datetime import datetime

__dir__ = os.path.dirname(__file__)
app = Flask(__name__)
app.config.update(yaml.safe_load(open(os.path.join(__dir__, 'config.yaml'))))

BABEL = Babel(app)


##############################################################
# LOGIN
##############################################################
@app.before_request
def init_profile():
    g.profiling = []


@app.before_request
def global_user():
    g.user = get_username()


@app.route('/login')
def login():
    next_page = request.args.get('next')
    if next_page:
        session['after_login'] = next_page

    client_key = app.config['CONSUMER_KEY']
    client_secret = app.config['CONSUMER_SECRET']
    base_url = 'https://commons.wikimedia.org/w/index.php'
    request_token_url = base_url + '?title=Special%3aOAuth%2finitiate'

    oauth = OAuth1Session(client_key,
                          client_secret=client_secret,
                          callback_uri='oob')
    fetch_response = oauth.fetch_request_token(request_token_url)

    session['owner_key'] = fetch_response.get('oauth_token')
    session['owner_secret'] = fetch_response.get('oauth_token_secret')

    base_authorization_url = 'https://commons.wikimedia.org/wiki/Special:OAuth/authorize'
    authorization_url = oauth.authorization_url(base_authorization_url,
                                                oauth_consumer_key=client_key)
    return redirect(authorization_url)


@app.route("/oauth-callback", methods=["GET"])
def oauth_callback():
    base_url = 'https://commons.wikimedia.org/w/index.php'
    client_key = app.config['CONSUMER_KEY']
    client_secret = app.config['CONSUMER_SECRET']

    oauth = OAuth1Session(client_key,
                          client_secret=client_secret,
                          resource_owner_key=session['owner_key'],
                          resource_owner_secret=session['owner_secret'])

    oauth_response = oauth.parse_authorization_response(request.url)
    verifier = oauth_response.get('oauth_verifier')
    access_token_url = base_url + '?title=Special%3aOAuth%2ftoken'
    oauth = OAuth1Session(client_key,
                          client_secret=client_secret,
                          resource_owner_key=session['owner_key'],
                          resource_owner_secret=session['owner_secret'],
                          verifier=verifier)

    oauth_tokens = oauth.fetch_access_token(access_token_url)
    session['owner_key'] = oauth_tokens.get('oauth_token')
    session['owner_secret'] = oauth_tokens.get('oauth_token_secret')
    next_page = session.get('after_login')

    return redirect(next_page)


##############################################################
# LOCALIZAÇÃO
##############################################################
# Função para pegar a língua de preferência do usuário
@BABEL.localeselector
def get_locale():
    if request.args.get('lang'):
        session['lang'] = request.args.get('lang')
    return session.get('lang', 'pt')


# Função para mudar a língua de exibição do conteúdo
@app.route('/set_locale')
def set_locale():
    next_page = request.args.get('return_to')
    lang = request.args.get('lang')

    session["lang"] = lang
    redirected = redirect(next_page)
    redirected.delete_cookie('session', '/item')
    return redirected


def pt_to_ptbr(lang):
    if lang == "pt" or lang == "pt-br":
        return "pt-br"
    else:
        return lang


##############################################################
# PÁGINAS
##############################################################
@app.errorhandler(400)
@app.errorhandler(401)
@app.errorhandler(403)
@app.errorhandler(404)
@app.errorhandler(405)
@app.errorhandler(406)
@app.errorhandler(408)
@app.errorhandler(409)
@app.errorhandler(410)
@app.errorhandler(411)
@app.errorhandler(412)
@app.errorhandler(413)
@app.errorhandler(414)
@app.errorhandler(415)
@app.errorhandler(416)
@app.errorhandler(417)
@app.errorhandler(418)
@app.errorhandler(422)
@app.errorhandler(423)
@app.errorhandler(424)
@app.errorhandler(429)
@app.errorhandler(500)
@app.errorhandler(501)
@app.errorhandler(502)
@app.errorhandler(503)
@app.errorhandler(504)
@app.errorhandler(505)
def page_not_found(e):
    return render_template('error.html')


@app.route('/')
@app.route('/home')
@app.route('/inicio')
def inicio():
    username = get_username()
    lang = pt_to_ptbr(get_locale())
    return render_template('inicio.html',
                           username=username,
                           lang=lang)


@app.route('/about')
@app.route('/sobre')
def sobre():
    username = get_username()
    lang = pt_to_ptbr(get_locale())
    with open(os.path.join(app.static_folder, 'queries.json'), encoding="utf-8") as category_queries:
        all_queries = json.load(category_queries)

    quantidade = query_quantidade(all_queries["Quantidade_de_objetos"]["query"])
    return render_template('sobre.html',
                           username=username,
                           lang=get_locale(),
                           number_works=quantidade)


@app.route('/tutorial')
def tutorial():
    username = get_username()
    lang = pt_to_ptbr(get_locale())
    return render_template('tutorial.html',
                           username=username,
                           lang=lang)


@app.route('/apps')
def apps():
    username = get_username()
    lang = pt_to_ptbr(get_locale())
    return render_template('apps.html',
                           username=username,
                           lang=lang)


@app.route('/colecao/<type>')
def colecao(type):
    username = get_username()
    lang = pt_to_ptbr(get_locale())
    with open(os.path.join(app.static_folder, 'queries.json'), encoding="utf-8") as category_queries:
        all_queries = json.load(category_queries)

    try:
        selected_query = all_queries[type]["query"]
        selection = query_by_type(selected_query)
        if lang == "en":
            descriptor = all_queries[type]["descriptor"]["en"]
        else:
            descriptor = all_queries[type]["descriptor"]["pt-br"]

        return render_template("colecao.html",
                               collection=selection,
                               username=username,
                               lang=lang,
                               descriptor=descriptor)
    except:
        return redirect(url_for('inicio'))


@app.route('/item/<qid>', methods=["GET"])
def item(qid):
    username = get_username()
    lang = pt_to_ptbr(get_locale())

    with open(os.path.join(app.static_folder, 'queries.json')) as category_queries:
        all_queries = json.load(category_queries)

    metadata_query = all_queries["Metadados"]["query"].replace("LANGUAGE", lang).replace("QIDDAOBRA", qid)
    next_qid_query = all_queries["Next_qid"]["query"].replace("QIDDAOBRA", qid)
    work_metadata = query_metadata_of_work(metadata_query, lang=lang)
    next_qid = query_next_qid(next_qid_query)

    if "category" in work_metadata:
        category_images = api_category_members(work_metadata["category"])
    else:
        category_images = []

    return render_template('item.html',
                           metadata=work_metadata,
                           category_images=category_images,
                           username=username,
                           lang=lang,
                           qid=qid,
                           next_qid=next_qid)


@app.route('/send_file', methods=["POST"])
def send_file():
    username = get_username()

    message = None

    if request.method == "POST":
        uploaded_file = request.files['file']
        form = request.form
        filename = uploaded_file.filename

        # Registrar respostas
        try:
            register_possible_sensitive_answers(form)
        except:
            pass

        # Enviar imagem
        data = upload_file(uploaded_file, filename, form, username)
        if "error" in data and data["error"]["code"] == "fileexists-shared-forbidden":
            message = gettext(u"Uma imagem com este exato título já existe. Por favor, reformule o título.")
        elif "upload" in data and "warnings" in data["upload"] and "duplicate" in data["upload"]["warnings"]:
            message = gettext(
                u"Esta imagem é uma duplicata exata da imagem https://commons.wikimedia.org/wiki/File:%(file_)s",
                file_=data["upload"]["warnings"]["duplicate"][0])
        elif "upload" in data and "warnings" in data["upload"] and "duplicate-archive" in data["upload"]["warnings"]:
            message = gettext(u"Esta imagem é uma duplicata exata de uma outra imagem que foi deletada da base.")
        elif "upload" in data and "warnings" in data["upload"] and "was-deleted" in data["upload"]["warnings"]:
            message = gettext(u"Uma outra imagem costumava utilizar este mesmo título. Por favor, reformule o título.")
        elif "upload" in data and "warnings" in data["upload"] and "exists" in data["upload"]["warnings"]:
            message = gettext(u"Uma imagem com este exato título já existe. Por favor, reformule o título.")
        elif "error" in data:
            message = data["error"]["code"]
        else:
            message = gettext(
                u"Imagem enviada com sucesso! Verifique suas contribuições clicando em seu nome de usuário(a).")
    return jsonify(message)


@app.route('/static/dados.json')
def check_user_static():
    username = get_username()
    if username not in app.config['SUPERUSERS']:
        return gettext(u"Você não tem permissão de acessar este arquivo.")
    else:
        return redirect(os.path.join(app.static_folder, 'dados.json'))


def register_possible_sensitive_answers(form):
    ambiente_, local_, utilidade_, obtencao_, historia_, image = "", "", "", "", "", ""
    username = get_username()
    today = datetime.today().strftime('%Y-%m-%dT%H:%M:%S')

    if "title" in form and request.files['file']:
        image = form["title"] + os.path.splitext(request.files['file'].filename)[1]

    if "ambiente_de_uso" in form:
        ambiente_ = form["ambiente_de_uso"]
    if "local_ambiente" in form:
        local_ = form["local_ambiente"]
    if "para_que_serve" in form:
        utilidade_ = form["para_que_serve"]
    if "como_obteve" in form:
        obtencao_ = form["como_obteve"]
    if "história_especial" in form:
        historia_ = form["história_especial"]

    with open(os.path.join(app.static_folder, 'dados.json'), encoding="utf-8") as file:
        values = json.load(file)

    if "respostas" in values and values["respostas"]:
        values["respostas"].append({
            "Username": username,
            "Timestamp": today,
            "Image": image,
            "Ambiente_de_uso": ambiente_,
            "Local_ambiente": local_,
            "Para_que_serve": utilidade_,
            "Como_obteve": obtencao_,
            "História_especial": historia_
        })
    with open(os.path.join(app.static_folder, 'dados.json'), 'w', encoding="utf-8") as file:
        json.dump(values, file, ensure_ascii=False)


##############################################################
# MAIN
##############################################################
if __name__ == '__main__':
    app.run()
