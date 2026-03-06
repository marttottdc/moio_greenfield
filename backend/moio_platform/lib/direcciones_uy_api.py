BASE_URL = "https://direcciones.ide.uy/"

CAPAS_POLIGONALES = "api/v1/geocode/capasPoligonales"

GEOCODE_AUTOCOMPLETE  = "/api/v1/geocode/candidates"
"""

https://direcciones.ide.uy/api/v1/geocode/candidates?limit=10&q=Edmundo%20bianchi%202475%2C%20MONTEVIDEO&soloLocalidad=false
"""

GEOCODE_FIND = "/api/v1/geocode/find"

"""
departamento
idcalle
idcalleEsq
inmueble
km
letra
localidad
manzana
nomvia
portal
ruta
solar
solartype *
type

https://direcciones.ide.uy/api/v1/geocode/find?departamento=Montevideo&idcalle=1&portal=7271&type=Direccion-Portal
"""

GEOCODE_PADRON = "/api/v1/geocode/direcPadron"
"""
Devuelve las direcciones seleccionando por padron dentro de un departamento y localidad 
https://direcciones.ide.uy/api/v1/geocode/direcPadron?departamento=Mandonado&limit=100&localidad=La%20Juanita&padron=1234
"""

GEOCODE_POIS = "/api/v1/geocode/direcPuntoNotable"
"""
Devuelve las direcciones seleccionando por POI (Punto de Interés) dentro de un departamento 
https://direcciones.ide.uy/api/v1/geocode/direcPuntoNotable?departamento=Montevideo&limit=100&nombre=shopping

"""

GEOCODE_RUTA_KM = "/api/v1/geocode/rutakm"
"""
Dado un ruta y km, se devuelve un punto ubicado sobre esa ruta.
https://direcciones.ide.uy/api/v1/geocode/rutakm?km=27&ruta=9
"""