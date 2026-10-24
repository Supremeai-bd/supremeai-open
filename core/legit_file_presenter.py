"""Backward-compatibility module forwarding to NaturalFilePresenter.

বাংলা সারসংক্ষেপ:
------------------
আগের কোনো কোড যদি `core.legit_file_presenter` ইম্পোর্ট করে, তা যেন না ভাঙ্গে।
আসল ক্লাসটি `core.natural_file_presenter`-এ স্থানান্তরিত করা হয়েছে।
"""

from core.natural_file_presenter import LegitFilePresenter, NaturalFilePresenter

__all__ = ["NaturalFilePresenter", "LegitFilePresenter"]
