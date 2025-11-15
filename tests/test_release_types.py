# -*- coding: utf-8 -*-
import pytest
from spotify_client import classify_release

def test_single_by_type():
    item = {"album_type": "single", "total_tracks": 2}
    assert classify_release(item) == "single"

def test_single_by_group():
    item = {"album_group": "single", "total_tracks": 3}
    assert classify_release(item) == "single"

def test_single_by_tracks_eq1():
    item = {"album_type": "album", "total_tracks": 1}
    assert classify_release(item) == "single"

def test_album_default():
    item = {"album_type": "album", "total_tracks": 10}
    assert classify_release(item) == "album"
