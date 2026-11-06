from pathlib import Path
import unicodedata
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / 'data/raw'
OUT = ROOT / 'data/processed'
OUT.mkdir(parents=True, exist_ok=True)
BBOX = (-67.5, -11, -59, -5)

def text_key(value):
    return ''.join(c for c in unicodedata.normalize('NFD', str(value).upper()) if unicodedata.category(c) != 'Mn').strip()

def numbers(series):
    return pd.to_numeric(series.astype('string').str.strip().str.replace(',', '.', regex=False), errors='coerce')

def dates(series):
    return pd.to_datetime(series, format='mixed', dayfirst=True, errors='coerce')

def utm(geom):
    return 31980 if geom.centroid.x < -60 else 31981

def session():
    s = requests.Session()
    s.mount('https://', HTTPAdapter(max_retries=Retry(total=3, backoff_factor=1, status_forcelist=[429,500,502,503,504])))
    return s

def read_chunks(path):
    return pd.read_csv(path, sep=';', dtype=str, chunksize=100000, encoding='utf-8-sig')
