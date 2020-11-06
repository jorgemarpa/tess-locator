"""Implements a database holding World Coordinate System (WCS) data for TESS.

The functions in this module serve to populate and query a simple single-file
data base which holds WCS data for TESS Full Frame Images across all sectors.

The WCS catalog is a DataFrame composed of six columns:
sector, camera, ccd, begin, end, wcs. 
"""
import itertools
import warnings
from functools import lru_cache
from pathlib import Path
from typing import List, Union
from tqdm import tqdm

import pandas as pd
from astropy.time import Time
from astropy.wcs import WCS
from pandas import DataFrame

from . import DATADIR, SECTORS, imagelist, log

# Where do we store all the WCS data?
WCS_CATALOG: Path = DATADIR / Path("tess-wcs-catalog.parquet")


def update_wcs_catalog(sectors: List[int] = None):
    """Write WCS data of all sectors to a Parquet file.

    This function is slow (few minutes) because it will download the header
    of a reference FFI for each sector/camera/ccd combination.
    """
    if sectors is None:
        sectors = range(1, SECTORS + 1)

    log.info(f"Writing {WCS_CATALOG}")
    summary = []
    iterator = itertools.product(sectors, [1, 2, 3, 4], [1, 2, 3, 4])
    for sector, camera, ccd in tqdm(iterator, len(sectors) * 4 * 4):
        images = imagelist.list_images(sector=sector, camera=camera, ccd=ccd)
        wcs = images[len(images) // 2].download_wcs().to_header_string(relax=True)
        data = {
            "sector": sector,
            "camera": camera,
            "ccd": ccd,
            "begin": images[0].begin,
            "end": images[-1].end,
            "wcs": wcs,
        }
        summary.append(data)
    df = pd.DataFrame(summary)
    df.to_parquet(WCS_CATALOG)


@lru_cache
def load_wcs_catalog() -> DataFrame:
    """Reads the DataFrame that contains all WCS data."""
    log.info(f"Reading {WCS_CATALOG}")
    return pd.read_parquet(WCS_CATALOG)


@lru_cache(maxsize=4096)
def get_wcs(sector: int, camera: int, ccd: int) -> WCS:
    """Returns a WCS object for a specific FFI ccd."""
    df = load_wcs_catalog()
    wcsstr = (
        df.query(f"sector == {sector} & camera == {camera} & ccd == {ccd}").iloc[0].wcs
    )
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="'datfix' made the change 'Set DATE-REF to '1858-11-17' from MJD-REF'.",
        )
        wcs = WCS(wcsstr)
    return wcs


@lru_cache
def get_sector_dates() -> DataFrame:
    """Returns a DataFrame with sector, begin, end."""
    db = load_wcs_catalog()
    begin = db.groupby("sector")["begin"].min()
    end = db.groupby("sector")["end"].max()
    return begin.to_frame().join(end)


@lru_cache
def time_to_sector(time: Union[str, Time]) -> int:
    """Returns the sector number for a given timestamp."""
    if isinstance(time, Time):
        time = time.iso

    dates = get_sector_dates()
    for row in dates.itertuples():
        if (time >= row.begin) & (time <= row.end):
            return row.Index

    return None
