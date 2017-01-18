import webapp2

class MainHandler(webapp2.RequestHandler):
   def get(self):
        self.response.write('<h1>Bienvenido!</h1>')
        self.response.write('<p>Este sitio es un ejemplo de una aplicaci&oacute;n hecha en Python</p>')
        self.response.write('<p>Hosteado por <b>Google Cloud Engine</b></p>')
   
app = webapp2.WSGIApplication([
   ('/', MainHandler)
], debug=True)