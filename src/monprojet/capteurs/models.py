from django.db import models

class Station(models.Model):
    id_stat = models.CharField(max_length=100, primary_key=True)
    last_position = models.CharField(max_length=100)
    last_timestamp = models.DateTimeField(null=True, blank=True)
    is_Sat = models.BooleanField(default=False)
    is_Wifi = models.BooleanField(default=False)
    is_Lora = models.BooleanField(default=False)
    is_LTE = models.BooleanField(default=False)
    artefacts = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'station'

class Unit(models.Model):
    desc = models.CharField(max_length=255)
    symb = models.CharField(max_length=50)
    name = models.CharField(max_length=100)

    class Meta:
        db_table = 'unit'

class Sensor(models.Model):
    id_sens = models.CharField(max_length=100, primary_key=True)
    station = models.ForeignKey(Station, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    last_value = models.FloatField(null=True, blank=True)
    last_timestamp = models.DateTimeField(null=True, blank=True)
    type = models.CharField(max_length=100)
    unit = models.CharField(max_length=20)
    freq = models.FloatField()

    class Meta:
        db_table = 'sensor'

class Data(models.Model):
    station = models.ForeignKey(Station, on_delete=models.CASCADE)
    sensor = models.ForeignKey(Sensor, on_delete=models.CASCADE)
    timestamp = models.DateTimeField()
    value = models.FloatField()

    class Meta:
        db_table = 'data'
