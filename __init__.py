
def classFactory(iface):
    from .basemap_2_geopackage import Basemap2Geopackage
    return Basemap2Geopackage(iface)