from jinja2 import Environment
from django.contrib.staticfiles.storage import staticfiles_storage
from django.urls import reverse


def jinja2_environment(**options):
    """jinja环境"""

    # 创建环境对象
    env = Environment(**options)

    # 自定义语法:{{ static('静态文件相对路径') }}   {{ url('路由的命名空间') }}
    env.globals.update({
        'static': staticfiles_storage.url,
        'url': reverse,  # 反向解析
    })

    # 返回环境对象
    return env


"""
确保可以使用模板引擎中的{{ url('') }} {{ static('') }}这类语句 
"""