# coding=utf-8
"""
Ingest data from the command-line.
"""
from __future__ import absolute_import, division

from __future__ import print_function
import logging
import uuid
from xml.etree import ElementTree
import re
from pathlib import Path
import yaml
from dateutil import parser
from datetime import timedelta, datetime
import rasterio.warp
import click
from osgeo import osr
import os
import json

_STATIONS = {'023': 'TKSC', '022': 'SGS', '010': 'GNC', '011': 'HOA',
             '012': 'HEOC', '013': 'IKR', '014': 'KIS', '015': 'LGS',
             '016': 'MGR', '017': 'MOR', '032': 'LGN', '019': 'MTI', '030': 'KHC',
             '031': 'MLK', '018': 'MPS', '003': 'BJC', '002': 'ASN', '001': 'AGS',
             '007': 'DKI', '006': 'CUB', '005': 'CHM', '004': 'BKT', '009': 'GLC',
             '008': 'EDC', '029': 'JSA', '028': 'COA', '021': 'PFS', '020': 'PAC'}

def band_name(path):
    name = path.stem
    layername = name
    print(path)
    if 'HH' in str(path):
        layername = 'hh_gamma0'
    if 'HV' in str(path):
        layername = 'hv_gamma0'
    if 'linci' in str(path):
        layername = 'incidence_angle'
    if 'mask' in str(path):
        layername = 'mask'
    if 'date' in str(path):
        layername = 'observation_date'
    return layername


def get_projection(path):
    with rasterio.open(str(path)) as img:
        left, bottom, right, top = img.bounds
        return {
            'spatial_reference': str(str(getattr(img, 'crs_wkt', None) or img.crs.wkt)),
            'geo_ref_points': {
                'ul': { 'x': left, 'y': top },
                'ur': { 'x': right, 'y': top },
                'll': { 'x': left, 'y': bottom },
                'lr': { 'x': right, 'y': bottom },
            }
        }


def get_coords(geo_ref_points, spatial_ref):
    spatial_ref = osr.SpatialReference(spatial_ref)
    t = osr.CoordinateTransformation(spatial_ref, spatial_ref.CloneGeogCS())

    def transform(p):
        lon, lat, z = t.TransformPoint(p['x'], p['y'])
        return {'lon': lon, 'lat': lat}

    return {key: transform(p) for key, p in geo_ref_points.items()}


def populate_coord(doc):
    proj = doc['grid_spatial']['projection']
    doc['extent']['coord'] = get_coords(proj['geo_ref_points'], proj['spatial_reference'])


def prep_dataset(fields, path):

    #with open(list(path.glob('*.json'))[0]) as json_data:
    #    alos2json = json.load(json_data)

    aos = datetime(2000+int(fields['tile_year']), int(fields['tile_month']), int(fields['tile_day']))
    los = aos
    fields['creation_dt'] = aos
    satellite = 'ALOS'
    platform = 'PALSAR Mosaic'
    if 'PALSAR2' in str(path):
        satellite = 'ALOS-2'
        platform = 'PALSAR-2 Mosaic'
    fields['satellite'] = satellite
    # Want five files, HH, HV, LINCI, MASK, date
    images = {
        band_name(im_path): {
            'path': str(im_path.relative_to(path))
        }
        for im_path in path.glob('*.tif') if "RGB" not in str(im_path)
    }
    doc = {
        'id': str(uuid.uuid4()),
        'processing_level': "terrain",
        'product_type': "gamma0",
        'creation_dt': aos,
        'platform': {
            'code': satellite  # Must match with product definition
        },
        'instrument': {
            'name': platform  # Must match with product definition
        },
        'acquisition': {
            'groundstation': {
                'code': '023',
                'aos': str(aos),
                'los': str(los)
            }
        },
        'extent': {
            'from_dt': str(aos),
            'to_dt': str(aos),
            'center_dt': str(aos)
        },
        'format': {
            'name': 'GeoTiff'
        },
        'grid_spatial': {
            'projection': get_projection(path / next(iter(images.values()))['path'])
        },
        'image': {
            'bands': images
        },
        'lineage': {
            'source_datasets': {},
        }
    }
    populate_coord(doc)
    return doc


def prepare_datasets(alos2_path):
    # Mosaic/2007_PALSAR_VietnamDC/N09E104_07_MOS/
    # N09E104_07_date.tif   N09E104_07_RGB.kmz    N09E104_07_sl_HV.tif
    # N09E104_07_linci.tif  N09E104_07_RGB.tif
    # N09E104_07_mask.tif   N09E104_07_sl_HH.tif
    print(alos2_path)
    fields = re.search(( r"(?P<latitude_dir>N|S)"
                         r"(?P<latitude>[0-9]{2})"
                         r"(?P<longitude_dir>E|W)"
                         r"(?P<longitude>[0-9]{3})"
                         "_"
                         r"(?P<tile_year>[0-9]{2})"), str(alos2_path)).groupdict()
    fields['tile_month'] = '12'
    fields['tile_day'] = '31'
    alos2 = prep_dataset(fields, alos2_path)
    return (alos2, alos2_path)


@click.command(help="Prepare ALOS1/2 PALSAR1/2 Mosaic dataset for ingestion into the Data Cube.")
@click.argument('datasets', type=click.Path(exists=True, readable=True, writable=True), nargs=-1)
def main(datasets):
    logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s', level=logging.INFO)

    for dataset in datasets:
        path = Path(dataset)

        logging.info("Processing %s", path)
        documents = prepare_datasets(path)

        dataset, folder = documents
        yaml_path = str(folder.joinpath('alos2-metadata.yaml'))
        logging.info("Writing %s", yaml_path)
        with open(yaml_path, 'w') as stream:
            yaml.dump(dataset, stream)

if __name__ == "__main__":
    main()
