import webapp2
import os
import jinja2
import cloudstorage
import mimetypes

from google.appengine.api import users
from google.appengine.api import images
from google.appengine.api import app_identity
from google.appengine.ext import ndb
from google.appengine.ext import blobstore

from models import Note
from models import CheckListItem
from models import NoteFile

jinja_env = jinja2.Environment(
  loader=jinja2.FileSystemLoader(os.path.dirname(__file__)))

images_formats = {
   '0': 'image/png',
   '1': 'image/jpeg',
   '2': 'image/webp',
   '-1': 'image/bmp',
   '-2': 'image/gif',
   '-3': 'image/ico',
   '-4': 'image/tiff',
}

class MainHandler(webapp2.RequestHandler):
    def get(self):
        user = users.get_current_user()
        if user is not None:
          logout_url = users.create_logout_url(self.request.uri)
          template_context = {
           'user': user.nickname(),
           'logout_url': logout_url,
          }
          self.response.out.write(
            self._render_template('main.html', template_context))
        else:
          login_url = users.create_login_url(self.request.uri) 
          self.redirect(login_url)
    
    def post(self):
        user = users.get_current_user()
        if user is None:
            self.error(401)

        bucket_name = app_identity.get_default_gcs_bucket_name()
        uploaded_file = self.request.POST.get('uploaded_file')
        file_name = getattr(uploaded_file, 'filename', None)
        file_content = getattr(uploaded_file, 'file', None);
        real_path = ''

        if file_name and file_content:
          content_t = mimetypes.guess_type(file_name)[0]
          real_path = os.path.join('/', bucket_name, user.user_id(), file_name)

          with cloudstorage.open(real_path, 'w', content_type=content_t, options={'x-goog-acl':'public-read'}) as f:
            f.write(file_content.read())

        self._create_note(user, file_name, real_path)

        logout_url = users.create_logout_url(self.request.uri)
        template_context = {
            'user': user.nickname(),
            'logout_url': logout_url,
        }
        self.response.out.write(
            self._render_template('main.html', template_context))

    def _render_template(self, template_name, context = None):
        if context is None:
            context = {}

        user = users.get_current_user()
        ancestor_key = ndb.Key("User", user.nickname())
        qry = Note.owner_query(ancestor_key)
        context['notes'] = qry.fetch()

        template = jinja_env.get_template(template_name)
        return template.render(context)

    def _get_urls_for(self, file_name):
      user = users.get_current_user()
      if user is None:
        return
      bucket_name = app_identity.get_default_gcs_bucket_name()
      path = os.path.join('/', bucket_name, user.user_id(), file_name)
      real_path = '/gs' + path
      key = blobstore.create_gs_key(real_path)

      try:
        url = images.get_serving_url(key, size=0)
        thumbnail_url = images.get_serving_url(key, size=150, crop=True)
      except images.TransformationError, images.NotImageError:
        url = "http://storage.googleapis.com{}".format(path)
        thumbnail_url = None

      return url, thumbnail_url

    @ndb.transactional
    def _create_note(self, user, file_name, file_path):
        note = Note(parent=ndb.Key("User", user.nickname()), title=self.request.get('title'), content=self.request.get('content'))
        note.put()

        item_titles = self.request.get('checklist_items').split(',')
        for item_title in item_titles:
            item = CheckListItem(parent=note.key, title=item_title)
            item.put()
            note.checklist_items.append(item.key)

        if file_name and file_path:
          url, thumbnail_url = self._get_urls_for(file_name)
          f = NoteFile(parent=note.key, name=file_name, url=url, thumbnail_url=thumbnail_url,full_path=file_path)
          f.put()
          note.files.append(f.key)

        note.put()

class MediaHandler(webapp2.RequestHandler):
  def get(self, file_name):
    user = users.get_current_user()
    bucket_name = app_identity.get_default_gcs_bucket_name()
    content_t = mimetypes.guess_type(file_name)[0]
    real_path = os.path.join('/', bucket_name, user.user_id(), file_name)

    try:
      with cloudstorage.open(real_path, 'r') as f:
        self.response.headers.add_header('Content-Type', content_t)
        self.response.out.write(f.read())
    except cloudstorage.errors.NotFoundError:
      self.abort(404)

class ShrinkHandler(webapp2.RequestHandler):
  def _shrink_note(self, note):
    for file_key in note.files:
      file = file_key.get()
      try:
        with cloudstorage.open(file.full_path) as f:
          image = images.Image(f.read())
          image.resize(640)
          new_image_data = image.execute_transforms()
        content_t = images_formats.get(str(image.format))
        with cloudstorage.open(file.full_path, 'w', content_type=content_t) as f:
          f.write(new_image_data)
      except images.NotImageError:
        pass

  def get(self):
    user = users.get_current_user()
    if user is None:
      login_url = users.create_login_url(self.request.uri)
      return self.redirect(login_url)

    ancestor_key = ndb.Key("User", user.nickname())
    notes = Note.owner_query(ancestor_key).fetch()

    for note in notes:
      self._shrink_note(note)

    self.response.write("Done,")

app = webapp2.WSGIApplication([
  (r'/', MainHandler),
  (r'/media/(?P<file_name>[\w.]{0,256})', MediaHandler),
  (r'/shrink', ShrinkHandler),
], debug=True)

