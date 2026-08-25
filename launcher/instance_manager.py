# -*- coding: utf-8 -*-
"""实例管理器：增删改查（进程管理见 process_manager）。"""
from .config import Config
from .instance import Instance
from .instance_scanner import probe


class InstanceManager:
    def __init__(self, config: Config):
        self.config = config

    # ---------- CRUD ----------
    def all(self) -> list:
        return [Instance.from_dict(d) for d in self.config.instances]

    def local_instances(self) -> list:
        return [i for i in self.all() if i.is_local]

    def get(self, uid: str):
        for d in self.config.instances:
            if d.get("uid") == uid:
                return Instance.from_dict(d)
        return None

    def add(self, inst: Instance) -> None:
        self.config.instances.append(inst.to_dict())
        self.config.save()

    def add_probe(self, path: str) -> Instance:
        """探测并添加一个本地实例（去重）。"""
        d = probe(path)
        for existing in self.config.instances:
            if existing.get("path", "").lower() == d["path"].lower():
                return Instance.from_dict(existing)
        inst = Instance.from_dict(d)
        self.config.instances.append(inst.to_dict())
        self.config.save()
        return inst

    def update(self, inst: Instance) -> None:
        for i, d in enumerate(self.config.instances):
            if d.get("uid") == inst.uid:
                self.config.instances[i] = inst.to_dict()
                break
        self.config.save()

    def remove(self, uid: str) -> None:
        self.config.instances = [d for d in self.config.instances
                                 if d.get("uid") != uid]
        self.config.save()
