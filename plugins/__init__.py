"""
    Copyright 2017 Inmanta

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

import uuid
from collections import defaultdict
import re

from inmanta import protocol
from inmanta.config import Config
from inmanta.plugins import plugin, Context, PluginMeta
from inmanta.execute.util import Unknown
from inmanta.export import Exporter, unknown_parameters


RECORD_CACHE= {}


def type_to_map(cls):
    type_map = {"type": str(cls), "attributes": {}, "options": {}}
    defaults = cls.get_default_values()
    attribute_options = defaultdict(dict)

    for name, attr in cls.attributes.items():
        obj = re.search("(.*)__(.*)", name)
        if name[0] == "_" and name in defaults and defaults[name] is not None:
            type_map["options"][name[1:]] = defaults[name].execute(None, None, None)

        elif obj:
            attr, opt = obj.groups()
            attribute_options[attr][opt] = defaults[name].execute(None, None, None)

        else:
            type_map["attributes"][name] = {"type": attr.type.__str__()}
            if name in defaults and defaults[name] is not None:
                type_map["attributes"][name]["default"] = defaults[name].execute(None, None, None)

    for attr in attribute_options.keys():
        if attr in type_map["attributes"]:
            type_map["attributes"][attr]["options"] = attribute_options[attr]

    return type_map


@plugin
def get(context: Context, name: "string", instance: "string"="") -> "any":
    """
        Get a parameter from the server
    """
    env = Config.get("config", "environment", None)

    if env is None:
        raise Exception("The environment of this model should be configured in config>environment")

    if instance not in RECORD_CACHE:
        record_id = uuid.UUID(instance)
        def call():
            return context.get_client().get_record(tid=env, id=record_id)

        result = context.run_sync(call)

        if result.code == 200:
            RECORD_CACHE[instance] = result.result["record"]["fields"]
        else:
            metadata={"type": "form", "record_id": instance}
            unknown_parameters.append({"parameter": name, "source": "form", "metadata": metadata})
            return Unknown(source=name)

    fields = RECORD_CACHE[instance]
    if name in fields:
        return fields[name]
    else:
        metadata={"type": "form", "record_id": instance}
        unknown_parameters.append({"parameter": name, "source": "form", "metadata": metadata})
        return Unknown(source=name)


@plugin
def instances(context: Context, instance_type: "string", expecting: "number"=0) -> "list":
    """
        Return a list of instances of the given type

        :param instance_type The entity to base the form on
        :param expecting The minimal number of parameters to expect
    """
    env = Config.get("config", "environment", None)
    instance_type = context.get_type(instance_type)

    if env is None:
        raise Exception("The environment of this model should be configured in config>environment")

    type_map = type_to_map(instance_type)
    def put_call():
        return context.get_client().put_form(tid=env, id=type_map["type"], form=type_map)
    context.run_sync(put_call)

    def list_call():
        return context.get_client().list_records(tid=env, form_type=type_map["type"],
                                                 include_record=True)
    result = context.run_sync(list_call)

    if result.code != 200:
        raise Exception("Failed to retrieve instances: " + result.result["message"])

    return_list = []
    for record in result.result["records"]:
        return_list.append(record["id"])
        RECORD_CACHE[record["id"]] = record["fields"]

    return return_list


@plugin
def one(context: Context, name: "string", entity: "string") -> "any":
    """
        Get a parameter from a form that can have only one instance.
    """
    env = Config.get("config", "environment", None)
    entity = context.get_type(entity)

    if env is None:
        raise Exception("The environment of this model should be configured in config>environment")

    type_map = type_to_map(entity)

    if "record_count" not in type_map["options"] or type_map["options"]["record_count"] != 1:
        raise Exception("one plugin can only be used on forms for which only one instance can exist.")

    if name not in type_map["attributes"]:
        raise Exception("%s is not defined in form %s" % (name, type_map["type"]))

    def put_call():
        return context.get_client().put_form(tid=env, id=type_map["type"], form=type_map)
    context.run_sync(put_call)

    def list_call():
        return context.get_client().list_records(tid=env, form_type=type_map["type"])
    result = context.run_sync(list_call)

    if result.code != 200:
        raise Exception(result.result)

    if result.code == 404 or len(result.result["records"]) == 0:
        if name in type_map["attributes"] and "default" in type_map["attributes"][name]:
            return type_map["attributes"][name]["default"]

        else:
            metadata = {"type": "form", "form": type_map["type"]}
            unknown_parameters.append({"parameter": name, "source": "form", "metadata": metadata})
            return Unknown(source=name)

    elif len(result.result["records"]) > 1:
        raise Exception("Only one record for form %s may exist, %d were returned." %
                        (type_map["type"], len(result.result["records"])))

    else:
        def get_call():
            return context.get_client().get_record(tid=env, id=result.result["records"][0]["id"])
        result = context.run_sync(get_call)

        if name in result.result["record"]["fields"]:
            return result.result["record"]["fields"][name]

        metadata = {"type": "form", "record_id": result.result["record"]["id"]}
        unknown_parameters.append({"parameter": name, "source": "form", "metadata": metadata})
        return Unknown(source=name)


@plugin
def report(context: Context, name: "string", value: "string"):
    """
        Set a param on the server
    """
    env = Config.get("config", "environment", None)

    if "inmanta.execute.util.Unknown" in value:
        return

    if env is None:
        raise Exception("The environment of this model should be configured in config>environment")

    def report_call():
        return context.get_client().set_param(tid=env, id=name, value=value, source="report",
                                      metadata={"type": "report"})
    return context.run_sync(report_call)
