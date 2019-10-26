from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render, redirect
from django.urls import reverse
from django.views import View
from django import http
from django_redis import get_redis_connection
import re, json, logging
from django.db import DatabaseError

from meiduo_mall.utils.response_code import RETCODE
from meiduo_mall.utils.views import LoginRequiredJSONMixin
from celery_tasks.email.tasks import send_verify_email
from users.models import User, Address
from users.utils import generate_verify_email_url, check_verify_email_token
from . import constants
# Create your views here.

# 创建日志输出器
logger = logging.getLogger('django')



class UserBrowseHistory(LoginRequiredJSONMixin, View):
    """用户浏览记录"""

    def post(self, request):
        """保存用户商品浏览记录"""
        # 接收参数
        # request.body得到bytes(字节)类型的请求体中的内容,decode变为字符串类型的json数据
        json_str = request.body.decode()


        # 校验参数
        # 保存sku_id到redis
        # 先去重
        # 再保存:最近浏览的商品在最前面




class UpdateTitleAddressView(LoginRequiredJSONMixin, View):
    """更新地址标题"""

    def put(self, request, address_id):
        """实现更新地址标题逻辑"""
        # 接收参数:title
        json_dict = json.loads(request.body.decode())
        title = json_dict.get('title')

        # 校验参数
        if not title:
            return http.HttpResponseForbidden('缺少title')

        try:
            # 查询当前要更新标题的地址
            address = Address.objects.get(id = address_id)
            # 将新的地址标题覆盖地址标题\
            address.title = title
            address.save()
        except Exception as e:
            logger.error(e)
            return http.JsonResponse({'code': RETCODE.DBERR, 'errmsg': '更新标题失败'})

            # 响应结果
        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': '更新标题成功'})


class DefaultAddressView(LoginRequiredJSONMixin, View):
    """设置默认地址"""

    def put(self, request, address_id):
        """实现设置默认地址逻辑"""
        try:
            # 查询出当前那个地址会作为登录用户的默认地址
            address = Address.objects.get(id = address_id)

            # 将指定的地址设置为当前登录用户的默认地址
            request.user.default_address = address
            request.user.save()
        except Exception as e:
            logger.error(e)
            return http.JsonResponse({'code':RETCODE.DBERR, 'errmsg':'设置默认地址失败'})
        return http.JsonResponse({'code':RETCODE.OK, 'errmsg':'设置默认地址成功'})


class UpdateDestoryAddressView(LoginRequiredJSONMixin, View):
    # 更新和删除地址

    def put(self, request, address_id):
        """更新地址"""
        # 接收参数
        json_dict = json.loads(request.body.decode())
        receiver = json_dict.get('receiver')
        province_id = json_dict.get('province_id')
        city_id = json_dict.get('city_id')
        district_id = json_dict.get('district_id')
        place = json_dict.get('place')
        mobile = json_dict.get('mobile')
        tel = json_dict.get('tel')
        email = json_dict.get('email')

        # 校验参数
        if not all([receiver, province_id, city_id, district_id, place, mobile]):
            return http.HttpResponseForbidden('缺少必传参数')
        if not re.match(r'^1[3-9]\d{9}$', mobile):
            return http.HttpResponseForbidden('参数mobile有误')
        if tel:
            if not re.match(r'^[a-z0-9][\w\.\-]*@[a-z0-9\-]+(\.[a-z]{2,5}){1,2}$', email):
                return http.HttpResponseForbidden('参数email有误')

        # 使用最新的地址信息覆盖指定的旧的地址信息
        try:
            Address.objects.filter(id=address_id).update(
                user=request.user,
                title=receiver,
                receiver=receiver,
                province_id=province_id,
                city_id=city_id,
                district_id=district_id,
                place=place,
                mobile=mobile,
                tel=tel,
                email=email
            )
        except Exception as e:
            logger.error(e)
            return http.JsonResponse({'code':RETCODE.DBERR, 'errmsg':'修改地址失败'})

        # 响应新的地址信息给前段渲染
        address = Address.objects.get(id=address_id)
        address_dict = {
            "id": address.id,
            "title": address.title,
            "receiver": address.receiver,
            "province": address.province.name,
            "city": address.city.name,
            "district": address.district.name,
            "place": address.place,
            "mobile": address.mobile,
            "tel": address.tel,
            "email": address.email
        }
        return http.JsonResponse({'code':RETCODE.OK, 'errmsg':'修改地址成功', 'address':address_dict})

    def delete(self, request, address_id):
        """删除地址"""
        # 实现指定地址的逻辑删除: is_delete=Ture
        try:
            address = Address.objects.get(id=address_id)
            address.is_deleted = True
            address.save()
        except Exception as e:
            logger.error(e)
            return http.JsonResponse({'code':RETCODE.DBERR, 'errmsg':'删除地址失败'})

        # 响应结果: code,errmsg
        return http.JsonResponse({'code':RETCODE.OK, 'errmsg':'删除地址成功'})


class AddressCreateView(LoginRequiredJSONMixin, View):
    """新增地址"""

    def post(self, reqeust):
        """实现新增地址逻辑"""

        # 判断用户地址数量是否超过上限：查询当前登录用户的地址数量
        # count = Address.objects.filter(user=reqeust.user).count()
        count = reqeust.user.addresses.count()  # 一查多，使用related_name查询
        if count > constants.USER_ADDRESS_COUNTS_LIMIT:
            return http.JsonResponse({'code': RETCODE.THROTTLINGERR, 'errmsg': '超出用户地址上限'})

        # 接收参数
        json_str = reqeust.body.decode()
        json_dict = json.loads(json_str)
        receiver = json_dict.get('receiver')
        province_id = json_dict.get('province_id')
        city_id = json_dict.get('city_id')
        district_id = json_dict.get('district_id')
        place = json_dict.get('place')
        mobile = json_dict.get('mobile')
        tel = json_dict.get('tel')
        email = json_dict.get('email')


        # 校验参数
        if not all([receiver, province_id, city_id, district_id, place, mobile]):
            return http.HttpResponseForbidden('缺少必传参数')
        if not re.match(r'^1[3-9]\d{9}$', mobile):
            return http.HttpResponseForbidden('参数mobile有误')
        if tel:
            if not re.match(r'^(0[0-9]{2,3}-)?([2-9][0-9]{6,7})+(-[0-9]{1,4})?$', tel):
                return http.HttpResponseForbidden('参数tel有误')
        if email:
            if not re.match(r'^[a-z0-9][\w\.\-]*@[a-z0-9\-]+(\.[a-z]{2,5}){1,2}$', email):
                return http.HttpResponseForbidden('参数email有误')

        # 保存用户传入的地址信息
        try:
            address = Address.objects.create(
                user=reqeust.user,
                title=receiver,  # 标题默认就是收货人
                receiver=receiver,
                province_id=province_id,
                city_id=city_id,
                district_id=district_id,
                place=place,
                mobile=mobile,
                tel=tel,
                email=email,
            )

            # 如果登录用户没有默认的地址，我们需要指定默认地址
            if not reqeust.user.default_address:
                reqeust.user.default_address = address
                reqeust.user.save()
        except Exception as e:
            logger.error(e)
            return http.JsonResponse({'code': RETCODE.DBERR, 'errmsg': '新增地址失败'})

            # 构造新增地址字典数据
        address_dict = {
            "id": address.id,
            "title": address.title,
            "receiver": address.receiver,
            "province": address.province.name,
            "city": address.city.name,
            "district": address.district.name,
            "place": address.place,
            "mobile": address.mobile,
            "tel": address.tel,
            "email": address.email
        }

        # 响应新增地址结果：需要将新增的地址返回给前端渲染
        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': '新增地址成功', 'address': address_dict})




class AddressView(LoginRequiredMixin, View):
    """用户收货地址"""

    def get(self, request):
        """查询并展示用户地址信息"""

        # 获取当前登录用户对象
        login_user = request.user
        # 使用当前登录用户和is_deleted=False作为条件查询地址数据
        addresses = Address.objects.filter(user=login_user, is_deleted=False)

        # 将用户地址模型列表转字典列表:因为JsonResponse和Vue.js不认识模型类型，只有Django和Jinja2模板引擎认识
        address_list= []
        for address in addresses:
            address_dict = {
                "id": address.id,
                "title": address.title,
                "receiver": address.receiver,
                "province": address.province.name,
                "city": address.city.name,
                "district": address.district.name,
                "place": address.place,
                "mobile": address.mobile,
                "tel": address.tel,
                "email": address.email
            }
            address_list.append(address_dict)

        # 构造上下文
        context = {
            'default_address_id': login_user.default_address_id,
            'addresses': address_list
        }

        return render(request, 'user_center_site.html', context)


class VerifyEmailView(View):
    """验证邮箱"""

    def get(self, request):
        # 接收参数
        token = request.GET.get('token')

        # 校验参数
        if not token:
            return http.HttpResponseForbidden('缺少token')

        # 从token中提取用户信息user_id ==> user
        user = check_verify_email_token(token)
        if not token:
            return http.HttpResponseBadRequest('无效的token')

        # 将用户的email_active字段设置为true
        try:
            user.email_active = True
            user.save()
        except Exception as e:
            logger.error(e)
            return http.HttpResponseServerError('激活邮箱失败')

        # 相应结果:重定向到用户中心
        return redirect(reverse('users:info'))



class EmailView(LoginRequiredJSONMixin, View):
    """添加邮箱"""

    def put(self, request):
        # 接收参数
        json_str = request.body.decode()  # body类型是bytes类型,转化为字符串
        json_dict = json.loads(json_str)
        email = json_dict.get('email')

        # 校验参数
        if not re.match(r'^[a-z0-9][\w\.\-]*@[a-z0-9\-]+(\.[a-z]{2,5}){1,2}$', email):
            return http.HttpResponseForbidden('参数email有误')

        # 将用户传入的邮箱保存到用户数据库的email字段中
        try:
            request.user.email = email
            request.user.save()
        except Exception as e:
            logger.error(e)
            return http.JsonResponse({'code':RETCODE.DBERR, 'errmsg':'添加邮箱失败'})

        # 异步发送验证邮件
        verify_url = generate_verify_email_url(request.user)
        # send_verify_email(email, verify_url) # 错误的写法
        send_verify_email.delay(email, verify_url)  # 一定要记得调用delay

        # 响应结果
        return http.JsonResponse({'code':RETCODE.OK, 'errmsg':'OK'})


class UserInfoView(LoginRequiredMixin, View):
    """用户中心"""
    def get(self, request):
        """提供用户中心页面"""
        # 如果LoginRequiredMixin判断出用户已登录，那么request.user就是登陆用户对象
        context = {
            'username':request.user.username,
            'mobile':request.user.mobile,
            'email':request.user.email,
            'email_active':request.user.email_active,
        }

        return render(request, 'user_center_info.html', context)


class LogoutView(View):
    """用户退出登录"""

    def get(self, request):
        """实现用户退出登录的逻辑"""
        # 清除状态保持
        logout(request)

        # 退出登录后重定向到首页
        response = redirect(reverse('contents:index'))

        # 删除cookis中的用户名
        response.delete_cookie('username')

        # 相应结果
        return response


class LoginView(View):
    """用户登录"""

    def get(self, request):
        """提供用户登录页面"""
        return render(request, 'login.html')

    def post(self, request):
        """实现用户登录逻辑"""
        # 接收参数,前端HTML标签别名
        username = request.POST.get('username')
        password = request.POST.get('password')
        remembered = request.POST.get('remembered')

        # 校验参数
        if not all([username, password]):
            return http.HttpResponseForbidden('缺少必传参数')
        if not re.match(r'^[a-zA-Z0-9_-]{5,20}$', username):
            return http.HttpResponseForbidden('请输入正确的用户名或手机号')
        if not re.match(r'^[0-9A-Za-z]{8,20}$', password):
            return http.HttpResponseForbidden('密码最少8位,最长20位')

        # 认证用户:试用账号查询账号是否存在,如果用户存在,校验密码是否正确
        user = authenticate(username = username, password = password)
        if user is None:
            return render(request, 'login.html', {'account_errmsg':'账号或密码错误'})

        # 状态保持
        login(request, user)
        # 使用remembered确定状态保持周期(实现记住登录)
        if remembered != 'on':
            # 没有记住登录:状态保持在浏览器会话结束后就会销毁
            request.session.set_expiry(0)  # 单位是秒
        else:
            # 记住登录:状态保持为两周,默认即为两周
            request.session.set_expiry(None)

        # 响应结果
        # 先取出next
        next = request.GET.get('next')
        if next:
            # 重定向到next
            response = redirect(next)
        else:
            # 重定向到首页
            response = redirect(reverse('contents:index'))

        # 为了实现在首页的右上角展示用户名信息，我们需要将用户名缓存到cookie中
        # response.set_cookie('key', 'val', 'expiry')
        response.set_cookie('username', user.username, max_age=3600 * 24 * 15)

        # 相应结果:重定向到首页
        return response


class MobileCountView(View):
    """判断手机号是否重复注册"""
    def get(self, request, mobile):
        """

        :param mobile: 手机号
        :return: json
        """
        count = User.objects.filter(mobile=mobile).count()
        return http.HttpResponse({'code':RETCODE.OK, 'errmsg':'OK', 'count':count})


class UsernameCountView(View):
    """判断用户名是否重复注册"""
    def get(self, request, username):
        """

        :param username:用户名
        :return: JSON
        """
        # 实现主体业务逻辑：使用username查询对应的记录的条数(filter返回的是满足条件的结果集)
        count = User.objects.filter(username=username).count()
        # 响应结果
        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK', 'count': count})


class RegisterView(View):
    """用户注册"""

    def get(self, request):
        """
        提供注册界面
        :param request: 请求对象
        :return: 注册界面
        """
        return render(request, 'register.html')


    def post(self, request):
        """
        实现用户注册
        :param request: 请求对象
        :return: 注册结果
        """
        # 接收参数
        username = request.POST.get('username')
        password = request.POST.get('password')
        password2 = request.POST.get('password2')
        mobile = request.POST.get('mobile')
        sms_code_client = request.POST.get('sms_code')
        allow = request.POST.get('allow')

        # 校验参数:前后端校验分开.避免恶意用户越过前段逻辑/要保证后端的安全,前后端的校验逻辑相同
        # 判断参数是否齐全:all([]):会校验列表中的元素是否为空,只要有一个为空则返回false
        if not all([username, password, password2, mobile, allow]):
            return http.HttpResponseForbidden('缺少必传参数')
        # 判断用户是否是5-20个字符
        if not re.match(r'^[a-zA-Z0-9_-]{5,20}$', username):
            return http.HttpResponseForbidden('请输入5-20个字符的用户名')
        # 判断密码是否是8-20个字符
        if not re.match(r'^[a-zA-Z0-9_-]{8,20}$', password):
            return http.HttpResponseForbidden('请输入8-20个字符的密码')
        # 判断两次输入的密码是否一致
        if password != password2:
            return http.HttpResponseForbidden('两次输入的密码不一致')
        # 判断手机号是否合法
        if not re.match(r'^1[3-9]\d{9}$', mobile):
            return http.HttpResponseForbidden('请输入正确的手机号')
        # 判断短信验证码输入是佛正确
        redis_conn = get_redis_connection('verify_code')
        sms_code_server = redis_conn.get('sms_%s' % mobile)
        if sms_code_server is None:
            return render(request, 'register.html', {'sms_code_errmsg': '无效的短信验证码'})
        if sms_code_client != sms_code_server.decode():
            return render(request, 'register.html', {'sms_code_errmsg': '输入短信验证码有误'})

        # 判断用户是否勾选了协议
        if allow != 'on':
            return http.HttpResponseForbidden('请勾选用户协议')

        # 保存注册数据:是注册业务的核心
        # User返回一个注册成功的用户对象
        try:
            user = User.objects.create_user(username=username, password=password, mobile=mobile)
        except DatabaseError:
            return render(request, 'register.html', {'register_errmsg':'注册失败'})


        # 实现状态保持:通过将认证的用户唯一标识信息写入浏览器的cookie和服务端的session中
        login(request, user)

        # 相应结果:重定向到首页
        response = redirect(reverse('contents:index'))

        # 为了实现在首页的右上角展示用户名,需要将用户名缓存到cookie中
        response.set_cookie('username', user.username, max_age=3600 * 24 * 15)

        # return http.HttpResponse('注册成功')
        return response


