"""Training-data builders: verified layouts + community idgames comments."""

from .comments import critic_target, records_from_file, tag_pillars
from .idgames import FileRecord, parse_idgames_page, sanitize_file
from .pack import build_pack, write_pack
from .sft import ChatRecord, dump_jsonl, load_jsonl
from .verified import build_verified_records

__all__ = [
    "ChatRecord",
    "FileRecord",
    "build_pack",
    "build_verified_records",
    "critic_target",
    "dump_jsonl",
    "load_jsonl",
    "parse_idgames_page",
    "records_from_file",
    "sanitize_file",
    "tag_pillars",
    "write_pack",
]
