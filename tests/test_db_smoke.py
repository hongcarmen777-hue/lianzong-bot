\
from pathlib import Path
import tempfile

from xiaopingguo.db import Database


def test_multi_show_and_groups():
    with tempfile.TemporaryDirectory() as td:
        db = Database(f"sqlite:///{Path(td) / 'test.db'}")
        db.create_all()

        eden = db.create_show("eden", "离开伊甸以后")
        next_show = db.create_show("next", "下一辆车")

        p1 = db.add_player(eden.id, "01", "甲")
        p2 = db.add_player(eden.id, "02", "乙")
        db.add_player(next_show.id, "01", "另一个01")

        db.bind_group("group-main", eden.id, "main", "大群")
        db.bind_group("group-p1", eden.id, "personal", "01｜甲", p1.id)

        assert db.get_group_binding("group-main").show_id == eden.id
        assert len(db.list_players(eden.id)) == 2
        assert len(db.list_players(next_show.id)) == 1

        db.bind_player_user(p1.id, "user-1")
        db.bind_player_user(p2.id, "user-2")

        letter = db.add_heart_letter(eden.id, p1.id, p2.id, "今晚谢谢你。")
        assert letter.delivered is False

        wish = db.add_wish(eden.id, p1.id, "想去海边散步")
        assert db.list_open_wishes(eden.id)[0].id == wish.id
