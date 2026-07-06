"""
Tests for the ENCORE knowledge-base ingestion path resolution and Rev 4/Rev 5 crosswalk
handling, added after adapting `ingest_encore.py` to the May 2026 ENCORE knowledge base
export (previously written for the September 2025 export).

The real ENCORE knowledge base is licensed content (Global Canopy & UNEP) and is not
committed to this repository -- these tests build small synthetic CSVs that mirror the
real export's folder layout, filenames, encoding quirks, and column schema instead.
"""
import json

import pandas as pd
import pytest

import ingest_encore as ie


def _write_knowledge_base(base_dir, folder_name="Updated ENCORE knowledge base May 2026"):
    """
    Build a minimal synthetic ENCORE export under `base_dir`, mirroring the real May 2026
    export's structure: a dated top-level folder, 'ENCORE files/06. Dependency mat
    ratings.csv' (UTF-8 BOM + a stray non-breaking-space byte, like the real export), and
    a crosswalk CSV with BOTH ISIC Rev 4 and Rev 5 columns side by side.
    """
    kb_dir = base_dir / folder_name
    (kb_dir / "ENCORE files").mkdir(parents=True)
    (kb_dir / "Crosswalk tables").mkdir(parents=True)

    # Dependency ratings: two ISIC classes, one ecosystem service column.
    # Encode with a UTF-8 BOM (utf-8-sig) and inject a raw non-breaking-space byte (0xA0)
    # into a free-text cell, reproducing the real export's encoding quirks. The quirk
    # byte is placed in a column that isn't used as a join key (an extra 'Notes' column)
    # so it exercises the encoding-robustness path without affecting the crosswalk join.
    ratings_csv = (
        "ISIC Unique code,ISIC Section,ISIC Division,ISIC Group,ISIC Class,Water supply,Notes\n"
        "A_1_11_111,Agriculture,Crop production,Growing of cereals,Growing of wheat,VH,ok\n"
        "A_1_11_112,Agriculture,Crop production,Growing of cereals,Growing of maize,L,see\xa0note\n"
    )
    ratings_path = kb_dir / "ENCORE files" / "06. Dependency mat ratings.csv"
    ratings_path.write_bytes(b"\xef\xbb\xbf" + ratings_csv.encode("latin-1"))

    # Crosswalk: Rev 4 columns match the ratings file's Section/Division/Group/Class;
    # Rev 5 columns are deliberately different, so a test that accidentally matched on
    # Rev 5 instead of Rev 4 would fail to join.
    crosswalk_df = pd.DataFrame([
        {
            "EXIOBASE": "Cultivation of wheat",
            "ISIC Rev. 4 Section": "Agriculture",
            "ISIC Rev. 4. Division": "Crop production",
            "ISIC Rev 4. Group": "Growing of cereals",
            "ISIC Rev 4. Class": "Growing of wheat",
            "ISIC Rev. 4 Unique Code": "A_1_11_111",
            "ISIC Rev. 5 Section": "DIFFERENT Agriculture",
            "ISIC Rev. 5. Division": "DIFFERENT Crop production",
            "ISIC Rev 5. Group": "DIFFERENT Growing of cereals",
            "ISIC Rev 5. Class": "DIFFERENT Growing of wheat",
            "ISIC Rev. 5 Unique Code": "X_1_11_111",
        },
        {
            "EXIOBASE": "Cultivation of maize",
            "ISIC Rev. 4 Section": "Agriculture",
            "ISIC Rev. 4. Division": "Crop production",
            "ISIC Rev 4. Group": "Growing of cereals",
            "ISIC Rev 4. Class": "Growing of maize",
            "ISIC Rev. 4 Unique Code": "A_1_11_112",
            "ISIC Rev. 5 Section": "DIFFERENT Agriculture",
            "ISIC Rev. 5. Division": "DIFFERENT Crop production",
            "ISIC Rev 5. Group": "DIFFERENT Growing of cereals",
            "ISIC Rev 5. Class": "DIFFERENT Growing of maize",
            "ISIC Rev. 5 Unique Code": "X_1_11_112",
        },
    ])
    crosswalk_path = kb_dir / "Crosswalk tables" / "EXIOBASE - NACE Rev. 2 - ISIC Rev. 4 - ISIC Rev. 5.csv"
    crosswalk_df.to_csv(crosswalk_path, index=False, encoding="utf-8-sig")

    return kb_dir


def test_find_knowledge_base_dir_globs_dated_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(ie, "EXIOBASE_DIR", tmp_path)
    _write_knowledge_base(tmp_path, folder_name="Updated ENCORE knowledge base May 2026")

    found = ie._find_knowledge_base_dir()
    assert found.name == "Updated ENCORE knowledge base May 2026"


def test_find_knowledge_base_dir_missing_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(ie, "EXIOBASE_DIR", tmp_path)
    with pytest.raises(FileNotFoundError):
        ie._find_knowledge_base_dir()


def test_load_dependency_materiality_ratings_handles_bom_and_bad_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(ie, "EXIOBASE_DIR", tmp_path)
    _write_knowledge_base(tmp_path)

    df = ie.load_dependency_materiality_ratings()
    # The BOM must not leak into the index name (the first column, set as index_col).
    assert df.index.name == "ISIC Unique code"
    assert list(df["Water supply"]) == ["VH", "L"]


def test_load_encore_exiobase_crosswalk_uses_rev4_not_rev5(tmp_path, monkeypatch):
    monkeypatch.setattr(ie, "EXIOBASE_DIR", tmp_path)
    _write_knowledge_base(tmp_path)

    df = ie.load_encore_exiobase_crosswalk()
    # Renamed to the plain column names the rest of the pipeline expects.
    assert set(["ISIC Section", "ISIC Division", "ISIC Group", "ISIC Class", "EXIOBASE"]) <= set(df.columns)
    # Values must come from Rev 4 (not the deliberately-different Rev 5 placeholders).
    assert "DIFFERENT" not in df["ISIC Section"].iloc[0]
    assert df.loc["A_1_11_111", "EXIOBASE"] == "Cultivation of wheat"


def test_full_ingest_pipeline_joins_and_grades_intensity(tmp_path, monkeypatch):
    """
    End-to-end: load ratings + crosswalk (May 2026 schema), join, and confirm
    build_encore_materiality produces graded (not just binary) intensities.
    """
    monkeypatch.setattr(ie, "EXIOBASE_DIR", tmp_path)
    _write_knowledge_base(tmp_path)

    dep_mat = ie.load_dependency_materiality_ratings()
    crosswalk = ie.load_encore_exiobase_crosswalk()
    dep_mat.index = dep_mat.index.astype(str)
    crosswalk.index = crosswalk.index.astype(str)

    dep_mat_joined = pd.merge(
        dep_mat, crosswalk,
        on=["ISIC Section", "ISIC Division", "ISIC Group", "ISIC Class"], how="left",
    )
    assert dep_mat_joined["EXIOBASE"].notna().all()

    ecosystem_services = [c for c in dep_mat.columns if "ISIC" not in c and c != "Notes"]
    exiobase_sectors = dep_mat_joined["EXIOBASE"].dropna().unique()
    output = ie.build_encore_materiality(dep_mat_joined, ecosystem_services, exiobase_sectors)

    water = next(e for e in output if e["service"] == "Water supply")
    intensities = {s["sector"]: s["intensity"] for s in water["sectors"]}
    # VH (wheat) must score strictly higher than L (maize) -- graded, not binary.
    assert intensities["Cultivation of wheat"] > intensities["Cultivation of maize"]
    assert intensities["Cultivation of wheat"] == pytest.approx(1.0)
    assert intensities["Cultivation of maize"] == pytest.approx(0.1)
