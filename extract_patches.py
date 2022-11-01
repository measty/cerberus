"""extract_patches.py

Patch extraction script.
"""

import logging
import os
import pathlib
import scipy.io as sio

import cv2
import joblib
import numpy as np
import pandas as pd
import tqdm
import yaml

from misc.patch_extractor import PatchExtractor
from misc.utils import log_info, recur_find_ext, rm_n_mkdir


def load_msk(base_name, ds_info):
    # ! wont work if different img shares
    # ! same base_name but has different content.
    mask_present = False
    if "msk_dir" in ds_info:
        msk_dir = ds_info["msk_dir"]
        msk_ext = ds_info["msk_ext"]
        file_path = "%s/%s%s" % (msk_dir, base_name, msk_ext)
        if os.path.exists(file_path):
            msk = cv2.imread(file_path)
            msk = cv2.cvtColor(msk, cv2.COLOR_BGR2GRAY)
            msk[msk > 0] = 1
            msk = np.expand_dims(msk, -1)
            mask_present = True
    if not mask_present:
        img_dir = ds_info["img_dir"]
        img_ext = ds_info["img_ext"]
        file_path = "%s/%s%s" % (img_dir, base_name, img_ext)
        img = cv2.imread(file_path)
        msk = np.full(img.shape[:2], 1, dtype=np.uint8)
        msk = msk[..., None]
    return msk

def load_img(base_name, ds_info):
    # ! wont work correct if different img shares
    # ! same base_name but has different conten.
    img_dir = ds_info["img_dir"]
    img_ext = ds_info["img_ext"]
    file_path = "%s/%s%s" % (img_dir, base_name, img_ext)
    img = cv2.imread(file_path)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    return img

def load_ann(basename, ds_info, ann_type_list, use_channel_list):
    ann_info_dict = ds_info["ann_info"]

    ann_list = []
    ch_code_list = []
    for ann_type in ann_type_list:
        if ann_type not in ann_info_dict:
            log_info(
                "`%s` has no annotation `%s` at dataset level." % (basename, ann_type)
            )
            continue
        ann_dir = ann_info_dict[ann_type]["ann_dir"]
        ann_ext = ann_info_dict[ann_type]["ann_ext"]
        ann_channel_code = ann_info_dict[ann_type]["channel_code"]
        file_path = "%s/%s%s" % (ann_dir, basename, ann_ext)
        if not os.path.exists(file_path):
            log_info("`%s` has no annotation `%s` file." % (basename, ann_type))
            continue

        ann = sio.loadmat(file_path)
        ann_inst_map = ann['inst_map']
        ann_id = np.squeeze(ann['id']).tolist()
        if isinstance(ann_id, int):
            ann_id = [ann_id]
    
        if "TYPE" in use_channel_list and "TYPE" in ann_channel_code:
            ann_class = np.squeeze(ann['class']).tolist()
            if isinstance(ann_class, int):
                ann_class = [ann_class]
            ann_class_map = np.zeros([ann_inst_map.shape[0], ann_inst_map.shape[1]])
            for i, val in enumerate(ann_id):
                tmp = ann_inst_map == val
                class_val = ann_class[i]
                ann_class_map[tmp] = class_val
        
            ann = np.dstack([ann_inst_map, ann_class_map])
        
        else:
            ann = ann_inst_map

        if len(ann.shape) == 2:
            ann = ann[..., None]  # to NHWC
        ch_indices = [
            ch_idx
            for ch_idx, ch_code in enumerate(ann_channel_code)
            if ch_code in use_channel_list
        ]
        if len(ch_indices) == 0:
            assert False, "Request channel `%s` but `%s` has `%s`" % (
                use_channel_list,
                file_path,
                ann_channel_code,
            )
        ann = ann[..., ch_indices]
        sub_ch_code_list = np.array(ann_channel_code)[ch_indices]
        sub_ch_code_list = [
            "%s-%s" % (ann_type, ch_code) for ch_code in sub_ch_code_list
        ]
        ann_list.append(ann)
        ch_code_list.extend(sub_ch_code_list)
    if len(ann_list) == 0:
        return None
    ann_list = np.concatenate(ann_list, axis=-1)
    return ann_list, ch_code_list


# -------------------------------------------------------------------------------------
if __name__ == "__main__":

    logging.basicConfig(
        level=logging.DEBUG,
        format="|%(asctime)s.%(msecs)03d| [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d|%H:%M:%S",
        handlers=[logging.StreamHandler()],
    )

    win_size = 996
    step_size = 448
    extract_type = "valid"
    save_root = "/root/lsf_workspace/train_data/mtl/patches/"

    use_channel_list = ["INST", "TYPE"]
    ann_type_list = ["Gland", "Lumen", "Nuclei"]

    # extract patches for these datasets
    ds_list = ["gland", "lumen", "nuclei"]
    xtractor = PatchExtractor(win_size, step_size)

    with open("dataset.yml") as fptr:
        ds_info_dict = yaml.full_load(fptr)

    # sanity check
    for ds in ds_list:
        if ds not in ds_info_dict:
            assert False, "Dataset `%s` is not defined in yml."

    # ! currently this scheme is used together with torch.utils.data.Dataset
    # ! however, loading large amount of files in Random manner and spreadly stored
    # ! accross storage is not scalable. Refer to torch WebDataset for alternative strategy

    for ds_name in ds_list:
        ds_info = ds_info_dict[ds_name]
        img_dir = ds_info["img_dir"]
        img_ext = ds_info["img_ext"]
        split_info = pd.read_csv(ds_info["split_info"])

        out_dir_root = "%s/%s" % (save_root, ds_name)
        # extract patches in separate directories according to the dataset split
        # nr_splits = ds_info["nr_splits"]
        nr_splits = 4
        for split_nr in range(nr_splits):
            out_dir_tmp = out_dir_root + "/split_%d/%d_%d" % (
                split_nr + 1,
                win_size,
                step_size,
            )
            # rm_n_mkdir(out_dir_tmp)

        file_path_list = recur_find_ext(img_dir, img_ext)

        pbar_format = "Process File: |{bar}| {n_fmt}/{total_fmt}[{elapsed}<{remaining},{rate_fmt}]"
        pbarx = tqdm.tqdm(
            total=len(file_path_list), bar_format=pbar_format, ascii=True, position=0
        )

        for file_idx, file_path in enumerate(file_path_list):
            basename = pathlib.Path(file_path).stem
            split_nr = split_info.loc[split_info["Filename"] == basename, "Split"].iloc[
                0
            ]
            # if split_nr <= nr_splits and split_nr > 0:
            if split_nr > 0:
                out_dir = out_dir_root + "/split_%d/%d_%d" % (
                    split_nr,
                    win_size,
                    step_size,
                )

                img = load_img(basename, ds_info)
                msk = load_msk(basename, ds_info)
                ann = load_ann(basename, ds_info, ann_type_list, use_channel_list)
                if ann is None:
                    # no annotation detected, skip
                    log_info("`%s` has no annotation `%s`." % (basename, ann_type_list))
                    continue
                ann, ch_code = ann

                img = np.concatenate([img, msk, ann], axis=-1)
                sub_patches = xtractor.extract(img, extract_type)

                pbar_format = "Extracting  : |{bar}| {n_fmt}/{total_fmt}[{elapsed}<{remaining},{rate_fmt}]"
                pbar = tqdm.tqdm(
                    total=len(sub_patches),
                    leave=False,
                    bar_format=pbar_format,
                    ascii=True,
                    position=1,
                )

                for idx, patch in enumerate(sub_patches):
                    patch_img = patch[..., :3]
                    patch_msk = patch[..., 3]
                    patch_ann = patch[..., 4:]

                    if np.sum(patch_msk) <= 0:
                        continue

                    joblib.dump(
                        {
                            "img": patch_img.astype(np.uint8),
                            "ann": patch_ann.astype(np.int32),
                            "channel_code": ch_code,
                        },
                        "%s/%s-%04d.dat" % (out_dir, basename, idx),
                    )
                    assert patch.shape[0] == win_size
                    assert patch.shape[1] == win_size
            pbar.update()
            pbar.close()

            pbarx.update()
        pbarx.close()