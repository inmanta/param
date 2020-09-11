"""
    Copyright 2018 Inmanta

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.

    Contact: code@inmanta.com
"""

import re
from collections import defaultdict

from inmanta.config import Config
from inmanta.plugins import Context, plugin

RECORD_CACHE = {}


def type_to_map(cls):
    type_map = {"type": str(cls), "attributes": {}, "options": {}}
    defaults = cls.get_default_values()
    attribute_options = defaultdict(dict)

    attributes = {}
    for name, attr in cls.attributes.items():
        attributes[name] = attr

    for parent in cls.get_all_parent_entities():
        if not (parent.name == "Entity" and parent.namespace.get_full_name() == "std"):
            for name, attr in parent.attributes.items():
                if name not in attributes:
                    attributes[name] = attr

    for name, attr in attributes.items():
        obj = re.search("(.*)__(.*)", name)
        if name[0] == "_" and name in defaults and defaults[name] is not None:
            type_map["options"][name[1:]] = defaults[name].execute(None, None, None)

        elif obj:
            attr, opt = obj.groups()
            attribute_options[attr][opt] = defaults[name].execute(None, None, None)

        else:
            type_map["attributes"][name] = {"type": attr.type.type_string()}
            if name in defaults and defaults[name] is not None:
                type_map["attributes"][name]["default"] = defaults[name].execute(
                    None, None, None
                )

    for attr in attribute_options.keys():
        if attr in type_map["attributes"]:
            type_map["attributes"][attr]["options"] = attribute_options[attr]
            if "modifier" not in type_map["attributes"][attr]["options"]:
                type_map["attributes"][attr]["options"]["modifier"] = "rw"

    return type_map


@plugin
def report(context: Context, name: "string", value: "string"):
    """
    This plugin reports a parameter to the server from the compile process. This can be used for
    `output` like parameter like in HEAT or TOSCA templates.

    The dashboard will explicitly show these values as well.

    :param name: The name/label of the value
    :param value: The value to report.
    """
    env = Config.get("config", "environment", None)

    if "inmanta.execute.util.Unknown" in value:
        return

    if env is None:
        raise Exception(
            "The environment of this model should be configured in config>environment"
        )

    def report_call():
        return context.get_client().set_param(
            tid=env, id=name, value=value, source="report", metadata={"type": "report"}
        )

    return context.run_sync(report_call)
