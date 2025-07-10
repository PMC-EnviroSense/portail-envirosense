from django.contrib import admin
from .models import Sensor, Station, Data, Unit

admin.site.register(Sensor)
admin.site.register(Station)
admin.site.register(Data)
admin.site.register(Unit)
