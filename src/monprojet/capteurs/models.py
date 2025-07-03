from django.db import models

class Capteur(models.Model):
    nom = models.CharField(max_length=100)
    date_installation = models.DateField()
    actif = models.BooleanField(default=True)

    def __str__(self):
        return self.nom
