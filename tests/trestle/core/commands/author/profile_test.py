# Copyright (c) 2021 IBM Corp. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Tests for the profile author module."""

import argparse
import pathlib
import shutil
import sys
from typing import Dict, Optional, Tuple

from _pytest.monkeypatch import MonkeyPatch

import pytest

from ruamel.yaml import YAML

from tests import test_utils

import trestle.oscal.profile as prof
from trestle.cli import Trestle
from trestle.common.err import TrestleError
from trestle.common.model_utils import ModelUtils
from trestle.core.catalog_interface import CatalogInterface
from trestle.core.commands.author.profile import ProfileAssemble, ProfileGenerate
from trestle.core.models.file_content_type import FileContentType
from trestle.core.profile_resolver import ProfileResolver

# test dicts are of form {'name_exp': [(name, exp_str)...], 'ref': ref_str, 'text': prose}
# the text is inserted on the line after ref appears
# then the assembled control is searched for exp_str in the prose of the named parts

markdown_name = 'my_md'
prof_name = 'my_prof'
md_name = 'my_md'
assembled_prof_name = 'my_assembled_prof'

my_guidance_text = """

## Control my_guidance

This is my_guidance.
"""

# just add a new addition
my_guidance_dict = {
    'name_exp': [('my_guidance', 'This is my_guidance.')], 'ref': 'carefully.', 'text': my_guidance_text
}

multi_guidance_text = my_guidance_text = """

## Control a_guidance

This is a_guidance.

## Control b_guidance

This is b_guidance.
"""
# add two additions
multi_guidance_dict = {
    'name_exp': [('a_guidance', 'This is a_guidance.'), ('b_guidance', 'This is b_guidance.')],
    'ref': 'logs.',
    'text': multi_guidance_text
}


def edit_files(control_path: pathlib.Path, set_parameters: bool, add_header: bool, guid_dict: Dict[str, str]) -> None:
    """Edit the files to show assemble worked."""
    assert control_path.exists()
    assert test_utils.insert_text_in_file(control_path, None, guid_dict['text'])
    # delete the value for prm_2 so the value is blank
    # replace the value for prm_3 with new value
    # delete entire line for prm_4
    if set_parameters and add_header:
        assert test_utils.delete_line_in_file(control_path, 'ac-1_prm_2')
        assert test_utils.delete_line_in_file(control_path, 'ac-1_prm_3')
        assert test_utils.delete_line_in_file(control_path, 'ac-1_prm_4')
        assert test_utils.insert_text_in_file(control_path, 'ac-1_prm_1', '  ac-1_prm_2:\n')
        assert test_utils.insert_text_in_file(control_path, 'ac-1_prm_2', '  ac-1_prm_3: new value\n')


def setup_profile_generate(trestle_root: pathlib.Path) -> Tuple[pathlib.Path, pathlib.Path, pathlib.Path, pathlib.Path]:
    """Set up files for profile generate."""
    nist_catalog_path = test_utils.JSON_TEST_DATA_PATH / test_utils.SIMPLIFIED_NIST_CATALOG_NAME
    trestle_cat_dir = trestle_root / 'catalogs/nist_cat'
    trestle_cat_dir.mkdir(exist_ok=True, parents=True)
    shutil.copy(nist_catalog_path, trestle_cat_dir / 'catalog.json')
    profile_dir = trestle_root / f'profiles/{prof_name}'
    profile_dir.mkdir(parents=True, exist_ok=True)
    # simple test profile sets values for ac-1 params 1-6 but not param_7
    simple_prof_path = test_utils.JSON_TEST_DATA_PATH / 'simple_test_profile.json'
    profile_path = profile_dir / 'profile.json'
    shutil.copy(simple_prof_path, profile_path)
    markdown_path = trestle_root / md_name
    ac1_path = markdown_path / 'ac/ac-1.md'
    assembled_prof_dir = trestle_root / f'profiles/{assembled_prof_name}'
    return ac1_path, assembled_prof_dir, profile_path, markdown_path


@pytest.mark.parametrize('add_header', [True, False])
@pytest.mark.parametrize('guid_dict', [my_guidance_dict, multi_guidance_dict])
@pytest.mark.parametrize('use_cli', [True, False])
@pytest.mark.parametrize('dir_exists', [True, False])
@pytest.mark.parametrize('set_parameters', [True, False])
def test_profile_generate_assemble(
    add_header: bool,
    guid_dict: Dict,
    use_cli: bool,
    dir_exists: bool,
    set_parameters: bool,
    tmp_trestle_dir: pathlib.Path,
    monkeypatch: MonkeyPatch
) -> None:
    """Test the profile markdown generator."""
    ac1_path, assembled_prof_dir, profile_path, markdown_path = setup_profile_generate(tmp_trestle_dir)
    yaml_header_path = test_utils.YAML_TEST_DATA_PATH / 'good_simple.yaml'

    # convert resolved profile catalog to markdown then assemble it after adding an item to a control
    if use_cli:
        test_args = f'trestle author profile-generate -n {prof_name} -o {md_name}'.split()
        if add_header:
            test_args.extend(['-y', str(yaml_header_path)])
        monkeypatch.setattr(sys, 'argv', test_args)
        assert Trestle().run() == 0

        edit_files(ac1_path, set_parameters, add_header, guid_dict)

        test_args = f'trestle author profile-assemble -n {prof_name} -m {md_name} -o {assembled_prof_name}'.split()
        if set_parameters:
            test_args.append('-sp')
        if dir_exists:
            assembled_prof_dir.mkdir()
        monkeypatch.setattr(sys, 'argv', test_args)
        assert Trestle().run() == 0
    else:
        profile_generate = ProfileGenerate()
        yaml_header = {}
        if add_header:
            yaml = YAML()
            yaml_header = yaml.load(yaml_header_path.open('r'))
        profile_generate.generate_markdown(tmp_trestle_dir, profile_path, markdown_path, yaml_header, False, None)

        edit_files(ac1_path, set_parameters, add_header, guid_dict)

        if dir_exists:
            assembled_prof_dir.mkdir()
        assert ProfileAssemble.assemble_profile(
            tmp_trestle_dir, prof_name, md_name, assembled_prof_name, set_parameters, False, None, None
        ) == 0

    # check the assembled profile is as expected
    profile: prof.Profile
    profile, _ = ModelUtils.load_top_level_model(tmp_trestle_dir, assembled_prof_name,
                                                 prof.Profile, FileContentType.JSON)
    # get the set_params in the assembled profile
    set_params = profile.modify.set_parameters
    sp_dict = {}
    for set_param in set_params:
        sp_dict[set_param.param_id] = set_param.values[0].__root__
    assert sp_dict
    assert sp_dict['ac-1_prm_1'] == 'all personnel'
    if set_parameters and add_header:
        assert 'ac-1_prm_2' not in sp_dict
        assert 'ac-1_prm_4' not in sp_dict
        assert sp_dict['ac-1_prm_3'] == 'new value'
    else:
        assert sp_dict['ac-1_prm_2'] == 'A thorough'
        assert sp_dict['ac-1_prm_3'] == 'officer'

    # now create the resolved profile catalog from the assembled json profile and confirm the addition is there

    catalog = ProfileResolver.get_resolved_profile_catalog(tmp_trestle_dir, assembled_prof_dir / 'profile.json')
    catalog_interface = CatalogInterface(catalog)
    # confirm presence of all expected strings in the control named parts
    for name, exp_str in guid_dict['name_exp']:
        prose = catalog_interface.get_control_part_prose('ac-1', name)
        assert prose.find(exp_str) >= 0


@pytest.mark.parametrize(
    'required_sections, success', [(None, True), ('a_guidance,b_guidance', True), ('a_guidance,c_guidance', False)]
)
@pytest.mark.parametrize('ohv', [True, False])
def test_profile_ohv(required_sections: Optional[str], success: bool, ohv: bool, tmp_trestle_dir: pathlib.Path) -> None:
    """Test profile generate assemble with overwrite-header-values."""
    ac1_path, assembled_prof_dir, profile_path, markdown_path = setup_profile_generate(tmp_trestle_dir)
    yaml_header_path = test_utils.YAML_TEST_DATA_PATH / 'good_simple.yaml'
    new_version = '1.2.3'

    # convert resolved profile catalog to markdown then assemble it after adding an item to a control
    # if set_parameters is true, the yaml header will contain all the parameters
    profile_generate = ProfileGenerate()
    yaml = YAML()
    yaml_header = yaml.load(yaml_header_path.open('r'))
    profile_generate.generate_markdown(tmp_trestle_dir, profile_path, markdown_path, yaml_header, ohv, None)

    edit_files(ac1_path, True, True, multi_guidance_dict)
    markdown_path = tmp_trestle_dir / md_name
    # change guidance in the other two controls but don't change header
    ac2_path = markdown_path / 'ac/ac-2.md'
    ac21_path = markdown_path / 'ac/ac-2.1.md'
    edit_files(ac2_path, False, False, multi_guidance_dict)
    edit_files(ac21_path, False, False, multi_guidance_dict)

    if success:
        assert ProfileAssemble.assemble_profile(
            tmp_trestle_dir, prof_name, md_name, assembled_prof_name, True, False, new_version, required_sections
        ) == 0

        # check the assembled profile is as expected
        profile: prof.Profile
        profile, _ = ModelUtils.load_top_level_model(
            tmp_trestle_dir, assembled_prof_name,
            prof.Profile,
            FileContentType.JSON
        )
        set_params = profile.modify.set_parameters
        sp_dict = {}
        for set_param in set_params:
            sp_dict[set_param.param_id] = set_param.values[0].__root__

        assert sp_dict
        assert sp_dict['ac-1_prm_1'] == 'all personnel'
        assert 'ac-1_prm_2' not in sp_dict
        assert sp_dict['ac-1_prm_3'] == 'new value'
        assert profile.metadata.version.__root__ == new_version

        catalog = ProfileResolver.get_resolved_profile_catalog(tmp_trestle_dir, assembled_prof_dir / 'profile.json')
        catalog_interface = CatalogInterface(catalog)
        # confirm presence of all expected strings in the control named parts
        for name, exp_str in multi_guidance_dict['name_exp']:
            prose = catalog_interface.get_control_part_prose('ac-1', name)
            assert prose.find(exp_str) >= 0
    else:
        with pytest.raises(TrestleError):
            ProfileAssemble.assemble_profile(
                tmp_trestle_dir, prof_name, md_name, assembled_prof_name, True, False, new_version, required_sections
            )


def test_profile_failures(tmp_trestle_dir: pathlib.Path, monkeypatch: MonkeyPatch) -> None:
    """Test failure modes of profile generate and assemble."""
    # disallowed output name
    test_args = 'trestle author profile-generate -n my_prof -o profiles -v'.split()
    monkeypatch.setattr(sys, 'argv', test_args)
    assert Trestle().run() == 1

    # no trestle root specified direct command
    test_args = argparse.Namespace(
        trestle_root=tmp_trestle_dir, name='my_prof', output='new_prof', verbose=0, set_parameters=False
    )
    profile_generate = ProfileGenerate()
    assert profile_generate._run(test_args) == 1

    # no trestle root specified
    profile_assemble = ProfileAssemble()
    assert profile_assemble._run(test_args) == 1

    # bad yaml
    bad_yaml_path = str(test_utils.YAML_TEST_DATA_PATH / 'bad_simple.yaml')
    trestle_root = str(tmp_trestle_dir)
    test_args = argparse.Namespace(
        trestle_root=trestle_root,
        name='my_prof',
        output='new_prof',
        yaml_header=bad_yaml_path,
        verbose=0,
        set_parameters=False
    )
    profile_generate = ProfileGenerate()
    assert profile_generate._run(test_args) == 1

    # profile not available for load
    test_args = 'trestle author profile-generate -n my_prof -o my_md -v'.split()
    monkeypatch.setattr(sys, 'argv', test_args)
    assert Trestle().run() == 1
