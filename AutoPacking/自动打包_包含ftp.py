# sudo pip3 install requests retry qrcode image qiniu
# gem install fir-cli

# scripts目录位于*.xcodeproj同级目录
# fir_token Ding_Hook_Url 需要更换
# adhoc.plist store.plist 需重新生成
# Build Settings中Code Signing描述文件是否匹配,Debug和Release必须都配置好
# 发布到app store需要修改开发者账号 develop_name develop_password
# 获取下载地址二维码需配置access_key secret_key bucket_name qiniu_domain
# 上传ftp需设置ftp_ip ftp_user ftp_pwd ftp_root_path
# Build Settings中Preprocessor Macros中 添加release宏isAppOnline=1用于替换isAppOnline，修改测试环境
# python3 FanbeiLoan/scripts/packingtool/AutoPackaging.py TEST(测试环境) origin/develop(分支) YES(是否发送钉钉消息) YES(是否上传ipa) YES(是否使用默认证书打包) $'1.' $'2.'(app更新内容， 多行文字, 行内不可加空格)

from PIL import Image
from ftplib import FTP
from retry import retry
from qiniu import Auth, put_file, etag
from DingHook import DingHook
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

import os
import re
import sys
import time
import hashlib
import subprocess
import random
import plistlib
import requests
import qrcode
import smtplib
import email.mime.multipart
import email.mime.text

################################################################################
# # 注意: 请配置下面的信息
################################################################################

# 服务器环境 不可修改 对应jenkins参数
server_infos = ['TEST', 'PRE_TEST', 'RELEASE']
# 其他证书打包
other_sign_plist = 'other_adhoc.plist'
other_sign_identity = 'iPhone Distribution: Huaiyang Boc Fullerton Community Bank'
# scripts根目录
scripts_path = 'scripts/'
# app store账号
develop_name = 'zhouyihua@edspay.com'
develop_password = 'Ald123456'
# fir token
fir_token = 'fe778f3d9f8b9dd5243fe4cb4e0ff242'
# qiniu
access_key = '9rhXOhTp-x6Y9eUlrB7mR_Hk0zDQLFv_VWwKKHWn'
secret_key = 'TpI9pdTlLQLB8hkWIS4fiEE98GM0yrre38lPw56Y'
bucket_name = 'firqr'
qiniu_domain = 'p64yljwwa.bkt.clouddn.com'
# ftp name pwd
ftp_ip = '192.168.106.226'
ftp_user = 'chanpin'
ftp_pwd = 'cp@123!'
ftp_root_path = '/客户端历史版本安装包/'
# email
smtp_host = 'smtp.mxhichina.com'
email_user = 'wangzonghui@edspay.com'
email_password = 'Ryan123456'
recipient_addresses = ''
# Bugly
bugly_app_id = '5eaeaab3d8' #DEBUG
bugly_app_key = 'b2ee11f3-1009-4fda-bf73-e5f812c824f3'


# 执行命令
def process_call(cmd, desc):
    ret = subprocess.call(cmd, shell=True)
    print('=======================================start=======================================')
    print(cmd)
    print('===================================================================================')
    print(desc, ['失败', '成功'][ret == 0])
    print('=========================================end=======================================')
    return ret


# 读取plist文件
def read_plist(path):
    print('read plist path: ', path)
    with open(path, 'rb') as f:
        datas = f.read()
    return plistlib.loads(datas)


# 创建ftp缓存目录
def make_cache_path(project_path):
    temp_path = get_build_cache_path(project_path)

    if os.path.exists(temp_path):
        clean_cmd = 'rm -r %s' % temp_path
        process_call(clean_cmd, '移除.buildcache目录')

    create_cmd = 'cd %s; mkdir .buildcache' % current_path
    process_call(create_cmd, '创建临时目录.buildcache')


def add_cache(project_path, project_scheme, server_info):
    build_path = get_build_path(project_path)
    ipa_path = os.path.join(build_path, '%s.ipa' % project_scheme)
    file_name = '%s.ipa' % server_info

    file_path = os.path.join(get_build_cache_path(project_path), file_name)
    
    move_cmd = 'mv %s %s' % (ipa_path, file_path,)
    return process_call(move_cmd, 'ipa移到cache目录')


# 创建ftp
@retry(tries=3, delay=1, jitter=2)
def ftpconnect(host, username, password):
    try:
        ftp = FTP()
        ftp.connect(host, 21)
        ftp.login(username, password)
        ftp.encoding = 'GBK'
        return ftp
    except:
        print('ftp登录失败')


# 创建ftp目录
def create_path(ftp, path, folders):
    for folder in folders:
        ftp.cwd(path)
        ftp_f_list = ftp.nlst()  #获取目录下文件、文件夹列表
        if folder not in ftp_f_list:
            ftp.mkd(folder)
        path = os.path.join(path, folder)


# ftp开始上传文件
@retry(tries=3, delay=1, jitter=2)
def start_upload_ftp(ftp, local_path, remote_path):
    try:
        print('local path:' + local_path)
        print('remote path:' + remote_path)
        buf_size = 1024
        fp = open(local_path, 'rb')
        ftp.storbinary('STOR ' + remote_path, fp, buf_size)
        ftp.set_debuglevel(0)
        fp.close()
    except:
        print('ftp上传文件失败')


# 上传ipa到ftp
def upload_ipas_to_ftp(ftp, project_path, project_scheme, app_name, app_version):
    cache_path = get_build_cache_path(project_path)

    path = ftp_root_path
    version_folder = app_version
    app_folder = '%s_iOS' % app_name
    create_path(ftp, path, [app_folder, version_folder])

    list = os.listdir(cache_path)
    for i in range(0,len(list)):
        file_path = os.path.join(cache_path,list[i])
        if os.path.isfile(file_path) and 'ipa' in file_path:
            local_path = file_path
            filename = '%s-(%s).ipa' % (os.path.basename(file_path), time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()))
            remote_path = os.path.join(path, app_folder, version_folder, filename)

            start_upload_ftp(ftp, local_path, remote_path)


# 邮箱登录
@retry(tries=3, delay=1, jitter=2)
def login_email():
    try:
        smtp = smtplib.SMTP()
        smtp.connect(smtp_host, '25')
        smtp.login(email_user, email_password)
        return smtp
    except:
        print('邮箱登录失败')


# 开始发送邮件
@retry(tries=3, delay=1, jitter=2)
def start_send_email(smtp, msg):
    try:
        smtp.sendmail(email_user, recipient_addresses, str(msg))
    except:
        print('邮件发送失败')


# 发送邮件
def send_email(app_name, app_version, project_path):
    if recipient_addresses == '':
        return

    cache_path = get_build_cache_path(project_path)

    smtp = login_email()

    subject = '%s_iOS_%s安装包' % (app_name, app_version)
    content = ''

    list = os.listdir(cache_path)
    for i in range(0,len(list)):
        file_path = os.path.join(cache_path,list[i])
        if os.path.isfile(file_path) and 'ipa' in file_path:

            msg = email.mime.multipart.MIMEMultipart()
            msg['from'] = email_user
            msg['to'] = recipient_addresses
            msg['subject'] = subject
            content = content
            txt = email.mime.text.MIMEText(content, 'plain', 'utf-8')
            msg.attach(txt)

            # 添加附件，传送文件
            part = MIMEApplication(open(file_path, 'rb').read())
            part.add_header('Content-Disposition', 'attachment', filename=os.path.basename(file_path))
            msg.attach(part)
            start_send_email(smtp, msg)

    smtp.quit()


# 上传测试 预发 线上包到ftp
def upload_to_ftp(project_path, project_scheme, git_branch, app_name, app_version):
    make_cache_path(project_path)
    for server_info in server_infos:
        cmd = 'python3 AutoPackaging.py %s %s NO NO' % (server_info, git_branch)
        if process_call(cmd, 'ipa打包') == 0:
            if add_cache(project_path, project_scheme, server_info) != 0:
                raise Exception('未找到ipa')

    ftp = ftpconnect(ftp_ip, ftp_user, ftp_pwd)
    upload_ipas_to_ftp(ftp, project_path, project_scheme, app_name, app_version)
    ftp.quit()

    title = get_title('', app_name, app_version)
    print('#KEY#FIR#%s#KEY#%s#KEY#%s#KEY#%s#KEY#FIR#' % (git_branch, title, '', ''))

#    send_email(app_name, app_version, project_path)


# 获取工作目录
def get_project_path():
    # 获取当前工程目录
    # 方案一
    # __file__ 当前文件
    # os.path.realpath 获取文件真实路径
    # os.path.dirname 获取目录
    # 方案二  打包之后  __file__ 获取失败  可通过  os.getcwd() os.path.abspath('.') os.path.abspath(os.curdir)
    current_path = os.path.dirname(os.path.realpath(__file__))
    os.chdir(current_path)
    upper_path = os.path.dirname(os.path.dirname(current_path))
    # 删除空格
    project_path = upper_path.strip()

    project_name = os.path.basename(upper_path)

    # 工程文件
    xcodeproj_path = upper_path + '/%s.xcodeproj' % project_name
    pbxproj_path = os.path.join(xcodeproj_path, 'project.pbxproj')
    
    # info.plist
    info_plist_path = upper_path + '/%s/info.plist' % project_name

    # entitlements
    entitlements_path = upper_path + '/%s/%s.entitlements' % (project_name, project_name)
    
    logo_path = upper_path + '/%s/Assets.xcassets/AppIcon.appiconset/iOS60@2x.png' % project_name

    return current_path, project_path, pbxproj_path, info_plist_path, logo_path, entitlements_path


# 获取build目录
def get_build_path(project_path):
    return os.path.join(project_path, 'build')


# 获取build目录
def get_build_cache_path(project_path):
    return os.path.join(get_build_path(project_path), '.buildcache')


# 获取dsymtool工具目录
def get_dsym_path(project_path):
    return os.path.join(project_path, scripts_path, 'dsymtool')


# 获取打包目录
def get_packing_path(project_path):
    return os.path.join(project_path, scripts_path, 'packingtool')


# 获取APP信息
def get_app_info(info_plist_path, pbxproj_path):
    pl = read_plist(info_plist_path)
    app_name = pl['CFBundleName']
    app_version = pl['CFBundleShortVersionString']
    app_build_version = pl['CFBundleVersion']

    return app_name, app_version, app_build_version


# 获取打包信息
def get_title(server_info, app_name, app_version):
    if server_info == 'RELEASE' or server_info == 'APP_STORE':
        server_string = '线上环境'
    elif server_info == 'PRE_TEST':
        server_string = '预发环境'
    elif server_info == 'TEST':
        server_string = '测试环境'
    else:
        server_string = ''
    title = '%s-iOS-v%s-%s' % (app_name, app_version, server_string)
    return title


# 替换服务器URL
def replace_server(pbxproj_path, server_type, is_use_default_plist, entitlements_path, code_sign_teamID):
    # 修改服务器URL
    replace_cmd = ("sed -i '' 's/\"isAppOnline=.*\"/\"isAppOnline=%i\"/g' " % server_type) + pbxproj_path
    replace_cmd2 = ("sed -i '' 's/YS_DYNAMIC_URL_KEY/\"isAppOnline=%i\"/g' " % server_type) + pbxproj_path
    process_call(replace_cmd, '替换服务器')
    process_call(replace_cmd2, '替换服务器2')
    
    if is_use_default_plist == 'NO':
        # 用其他证书打包时关闭推送选项
        push_cmd = ("sed -i '' 's/<key>aps-environment<\/key>/<key>1<\/key>/g' ") + entitlements_path
        push_cmd1 = ("sed -i '' 's/<string>development<\/string>/<string>1<\/string>/g' ") + entitlements_path
        process_call(push_cmd, '关闭推送')
        process_call(push_cmd1, '关闭推送1')

        # 用其他证书打包时替换teamID
        replace_teamID_cmd = ("sed -i '' 's/DevelopmentTeam = .*;/DevelopmentTeam = %s;/g' " % code_sign_teamID) + pbxproj_path
        replace_teamID_cmd1 = ("sed -i '' 's/DEVELOPMENT_TEAM = .*;/DEVELOPMENT_TEAM = %s;/g' " % code_sign_teamID) + pbxproj_path
        process_call(replace_teamID_cmd, '替换teamID')

        # 用其他证书打包时替换PROVISIONING_PROFILE
#        PROVISIONING_PROFILE = "a52136bd-d9e9-4d51-8ab3-0fa07ae52d2b";
#        PROVISIONING_PROFILE_SPECIFIER = "通用adhoc";


# 服务器参数替换回来
def replace_back_server(pbxproj_path, server_type, is_use_default_plist, entitlements_path, app_origin_teamID):
    # 修改服务器URL
    replace_cmd = ("sed -i '' 's/\"isAppOnline=.*\"/YS_DYNAMIC_URL_KEY/g' ") + pbxproj_path
    process_call(replace_cmd, '服务器参数替换回来')

    if is_use_default_plist == 'NO':
        # 用其他证书打包时打开推送选项
        push_cmd = ("sed -i '' 's/<key>1<\/key>/<key>aps-environment<\/key>/g' ") + entitlements_path
        push_cmd1 = ("sed -i '' 's/<string>1<\/string>/<string>development<\/string>/g' ") + entitlements_path
        process_call(push_cmd, '关闭推送')
        process_call(push_cmd1, '关闭推送')

        # 用其他证书打包时替换teamID
        replace_teamID_cmd = ("sed -i '' 's/DevelopmentTeam = .*;/DevelopmentTeam = %s;/g' " % app_origin_teamID) + pbxproj_path
        replace_teamID_cmd1 = ("sed -i '' 's/DEVELOPMENT_TEAM = .*;/DEVELOPMENT_TEAM = %s;/g' " % app_origin_teamID) + pbxproj_path
        process_call(replace_teamID_cmd, '替换teamID')
        process_call(replace_teamID_cmd1, '替换teamID1')


# 获取当前证书配置信息 UUID
# def get_certificate_information(file_name, key_characters):
#     """获取profile路径，通过命令获取到profile的plist信息，通过字符串查找获取到plist中的 UUID、application-identifier、com.apple.developer.team-identifier等信息"""
#     # 对证书使用 security cms -D -i %s 或 /usr/bin/security cms -D -i 可以获取描述文件的plist信息
#     certificate_file = os.popen('security cms -D -i %s' % file_name)
#     certificate_string = certificate_file.read()
#     bytes_cer_string = bytes(certificate_string, encoding="utf-8")
#     cer_plist = plistlib.loads(bytes_cer_string)
#     certificate_file.close()
#
#     # 查找plist文件中的 key_characters 字段
#     return cer_plist[key_characters]

# 动态获取当前证书配置信息
def get_project_info(project_path,  file_path, plist_name,):
    with open(file_path, 'r', encoding='UTF-8') as f:
        pbxproj = f.read()
    code_sign_identity = re.findall(r'CODE_SIGN_IDENTITY = "(.*?)\s\(.*?\)"', pbxproj)[1]

    app_bundleid = re.findall(r'PRODUCT_BUNDLE_IDENTIFIER = (.+?);', pbxproj)[0]
    app_origin_teamID = re.findall(r'DevelopmentTeam = (.+?);', pbxproj)[0]

    profile_plist_path = os.path.join(get_packing_path(project_path), plist_name)
    pl = read_plist(profile_plist_path)
    provisioning_profile_specifier = pl['provisioningProfiles'][app_bundleid]
    code_sign_teamID = pl['teamID']

    return code_sign_identity, provisioning_profile_specifier, app_bundleid, app_origin_teamID, code_sign_teamID


# 获取当前scheme
def get_scheme():
    scheme_file = os.popen('cd ../..;xcodebuild -list')
    scheme_string = scheme_file.read()
    scheme_file.close()

    string_location1 = scheme_string.find('\n', scheme_string.find('Schemes:\n        ') + len('Schemes:\n        '))
    scheme = scheme_string[scheme_string.find('Schemes:\n        ') + len('Schemes:\n        '):string_location1]
    return scheme


# 获取fir app的最新一条下载地址
def get_fir_release_url(fir_short_path):
    latest_url = 'https://download.fir.im/%s' % fir_short_path;
    json = requests.get(latest_url).json()
    release_id = json['app']['releases']['master']['id']
    return 'https://fir.im/%s?release_id=%s' % (fir_short_path, release_id)


# 上传到appstore
@retry(tries=3, delay=1, jitter=2)
def upload_store(ipa_path):
    altool = '/Applications/Xcode.app/Contents/Applications/Application\ Loader.app/Contents/Frameworks/ITunesSoftwareService.framework/Versions/A/Support/altool'
    
    invalid_cmd = '%s -v -f %s -u %s -p %s -t ios --output-format xml' % (altool, ipa_path, develop_name, develop_password)
    upload_cmd = '%s --upload-app -f %s -t ios -u %s -p %s -t ios --output-format xml' % (altool, ipa_path, develop_name, develop_password)
    
    process_call(invalid_cmd, '验证IPA')
    ret = process_call(upload_cmd, '上传APP到AppStore')
    if ret != 0:
        raise Exception('上传到AppStore失败')


# 上传到fir
@retry(tries=3, delay=1, jitter=2)
def upload_fir(ipa_path, short_path):
    fir_cmd = 'fir publish %s --token=%s --short=%s -Q' % (ipa_path, fir_token, short_path)
    ret = process_call(fir_cmd, '上传ipa到fir')
    if ret != 0:
        raise Exception('上传到fir失败')


# 获取下载地址
def get_fir_url(ipa_path, app_bundleid):
    fir_path = app_bundleid + fir_token
    short_path = (hashlib.md5(fir_path.encode('utf-8')).hexdigest())[8:-8]
    print(app_bundleid, fir_token, short_path)
    
    upload_fir(ipa_path, short_path)
    fir_url = get_fir_release_url(short_path)
    
    print('上传成功 fir_url = %s' % fir_url)
    return fir_url


# 钉钉提交appstore消息
def send_store_message(title, git_branch):
    print('#KEY#FIR#%s#KEY#%s#KEY#%s#KEY#%s#KEY#FIR#' % (git_branch, title, '', ''))

    # 标题
    fir_title = '#### %s\n' % title
    # 分支
    fir_branch_text = '###### -- (%s)\n' % git_branch
    # 更新内容
    fir_update_content = '> AppStore上传成功\n\n'
    
    text = fir_title + fir_branch_text + fir_update_content
    send_ding_message(title, text, '')


# 二维码添加logo
def add_logo(img, logo_path):
    if not os.path.exists(logo_path):
        return img
    #设置二维码为彩色
    img = img.convert("RGBA")
    icon = Image.open(logo_path)
    w, h = img.size
    factor = 6
    size_w = int(w / factor)
    size_h = int(h / factor)
    icon_w, icon_h = icon.size
    if icon_w > size_w:
        icon_w = size_w
    if icon_h > size_h:
        icon_h = size_h
    icon = icon.resize((icon_w, icon_h), Image.ANTIALIAS)
    w = int((w - icon_w) / 2)
    h = int((h - icon_h) / 2)
    margin = int(6)
    icon = icon.convert("RGBA")
    newimg = Image.new("RGBA", (icon_w + margin, icon_h + margin), (255, 255, 255))
    img.paste(newimg, (w-int(margin/2), h-int(margin/2)), newimg)
    img.paste(icon, (w, h), icon)
    return img


# 生成二维码
def make_qr(fir_url, project_path, logo_path):
    if fir_url == '':
        return ''
    image_path = os.path.join(get_build_path(project_path), 'firqr.png')
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=2, border=3)
    qr.add_data(fir_url)
    qr.make(fit=True)
    add_logo(qr.make_image(), logo_path).save(image_path)
    return image_path


# 上传二维码到qiniu
def get_qr_image(image_path, app_bundleid):
    if image_path == '':
        return ''
    current_time = int(time.time()*1000)
    key = 'firqr_%s_%s_%d' % (app_bundleid, current_time, random.randint(0, 100000))
    image_key = hashlib.md5(key.encode('utf-8')).hexdigest()

    q = Auth(access_key, secret_key)

    #生成上传 Token，可以指定过期时间等
    token = q.upload_token(bucket_name, image_key, 3600)
    ret, info = put_file(token, image_key, image_path)
    print(info)
    image_url = ''
    if ret['key'] == image_key and ret['hash'] == etag(image_path):
        image_url = 'http://%s/%s' % (qiniu_domain, image_key)
    return image_url


# 上传dysm文件
def upload_dsym(project_path, app_version, app_build_version, app_bundleid):
    version = '%s(%s)' % (app_version, app_build_version)

    dsym_cache_path = os.path.join(get_dsym_path(project_path), '.dsymcache')

    dsym_file_path = ''
    dsym_file_name = ''
    
    print('dsym_cache_path: ', dsym_cache_path)
    
    if not os.path.exists(dsym_cache_path):
        print('dsym cache路径不存在')
        return
    
    list = os.listdir(dsym_cache_path)
    for i in range(0, len(list)):
        dsym_file_path = os.path.join(dsym_cache_path,list[i])
        dsym_file_name = os.path.basename(dsym_file_path)

    if dsym_file_path == '':
        return

    dsym_url = 'http://bugly.qq.com/upload/dsym?app=%s&pid=2&ver=%s&n=%s&key=%s&bid=%s' % (bugly_app_id, version, dsym_file_name, bugly_app_key, app_bundleid)

    dsym_cmd = 'curl --header "Content-Type:application/zip" --data-binary "@%s" "%s" --verbose' % (dsym_file_path, dsym_url)
    process_call(dsym_cmd, '上传dsym到Bugly')


# 钉钉测试消息
def send_dev_message(fir_url, git_branch, ding_send_texts, title, app_bundleid, project_path, is_send_ding, logo_path):
    image_path = make_qr(fir_url, project_path, logo_path)
    image_url = get_qr_image(image_path, app_bundleid)
    
    print('#KEY#FIR#%s#KEY#%s#KEY#%s#KEY#%s#KEY#FIR#' % (git_branch, title, fir_url, image_url))

    if is_send_ding == 'NO':
        return
    if fir_url == '':
        return

    # 标题
    fir_title = '#### %s\n' % title
    # 分支
    fir_branch_text = '###### -- (%s)\n' % git_branch
    # 更新内容
    fir_update_content = ''
    if len(ding_send_texts):
        fir_update_content = '> 更新内容:\n\n'
        for ding_text in ding_send_texts:
            fir_update_content += '> %s\n\n' % ding_text

    # 二维码
    fir_image = ''
    if image_url != '':
        fir_image = '> ![screenshot](%s)\n\n' % image_url
    # 下载地址
    fir_download_url = '> ######  [====下载地址====](%s)\n\n' % fir_url
    # 提示
    fir_tip_text = ''
#    if 'release_id' in fir_url:
#        fir_tip_text = '> ###### (%s下载地址不会被覆盖) \n\n' % (['', '二维码和'][fir_image != ''])

    text = fir_title + fir_branch_text + fir_update_content + fir_image + fir_download_url + fir_tip_text

    send_ding_message(title, text, fir_url)


# 发送钉钉消息
def send_ding_message(title, text, fir_url):
    print('准备发送钉钉消息:%@', text)
    dh = DingHook()
    dh.post_qrCode(title=title, text=text, messageurl=fir_url)


# 获取发布类型
def get_publish_info(server_info):
    server_type = 0
    publish_appstore = 0
    if server_info == 'RELEASE':
        server_type = 1
    elif server_info == 'PRE_TEST':
        server_type = 2
    elif server_info == 'APP_STORE':
        server_type = 1
        publish_appstore = 1
        assert server_type == 1 and 'master' in git_branch, '发布到AppStore必须要在master分支，线上环境'
    else:
        server_type = 0
    return server_type, publish_appstore


# 步骤一  清理项目缓存及ipa   创建新build目录
def clean_project_build(project_path):
    cmd = 'cd %s;xcodebuild clean' % project_path   # cd到路径，执行缓存清理 clean命令
    process_call(cmd, '清理build缓存')
    
    build_path = get_build_path(project_path)  # 配置build路径

    if os.path.exists(build_path):  # 如果build路径不为nil，移除build路径文件
        clean_cmd = 'rm -r %s' % build_path
        process_call(clean_cmd, '移除build目录')
    
    create_cmd = 'cd %s;mkdir build' % project_path
    process_call(create_cmd, '创建build目录')


# pod update
def pod_update(project_path):
    cmd = 'cd %s;pod update --verbose --no-repo-update' % project_path
    process_call(cmd, 'pod update ')


# 步骤二 构建版本
def build_workspace(project_path, project_scheme, configuration, project_team, profile_name):

    project_name = os.path.basename(project_path)
    build_xcarchive = '%s/%s.xcarchive' % (get_build_path(project_path), project_name)
    print('构建版本配置： %s' % build_xcarchive)

    # 方式一 没有.xcworkspace执行
    # buildCmd = 'xcodebuild -project %s.xcodeproj -scheme %s -sdk iphoneos -configuration Release clean archive -archivePath %s  CODE_SIGN_IDENTITY="%s" PROVISIONING_PROFILE="%s"' % (project_scheme, project_scheme,build_xcarchive,project_team, project_uuid)
    # 方式一 有.xcworkspace执行
    # buildCmd = 'cd ../..;xcodebuild -workspace %s.xcworkspace -scheme %s -sdk iphoneos -configuration %s clean archive -archivePath %s  CODE_SIGN_IDENTITY="%s" PROVISIONING_PROFILE="%s"' % (
    # project_scheme, project_scheme, configuration, build_xcarchive, project_team, project_uuid)
    build_cmd = 'cd ../..;xcodebuild -workspace %s.xcworkspace -scheme %s -sdk iphoneos -configuration %s clean archive -archivePath %s  CODE_SIGN_IDENTITY="%s" PROVISIONING_PROFILE_SPECIFIER="%s"' % (project_name, project_scheme, configuration, build_xcarchive, project_team, profile_name)
    
    if process_call(build_cmd, '构建版本') != 0:
        raise Exception('构建版本失败')


# 步骤三 生成配置ipa包
def build_ipa(project_path, option_plist, project_scheme):
    build_path = get_build_path(project_path)
    project_name = os.path.basename(project_path)
    if os.path.exists(build_path):
        sign_cmd = 'xcodebuild -exportArchive -archivePath %s/%s.xcarchive -exportOptionsPlist %s -exportPath %s' % (
            build_path, project_name, option_plist, build_path)
        
        if process_call(sign_cmd, '导出ipa') != 0:
            raise Exception('导出ipa失败')
        
        ipa_path = os.path.join(build_path, '%s.ipa' % project_scheme)
        return ipa_path
    else:
        raise Exception('没有找到app文件')


# 步骤四  上传ipa
def upload_ipa(ipa_path, app_bundleid, publish_appstore, is_upload):
    if is_upload == 'NO':
        return ''
    fir_url = ''
    if not os.path.exists(ipa_path):
        return fir_url
    print('准备上传ipa %s ' % ipa_path)
    if publish_appstore == 1:
        upload_store(ipa_path)
        return fir_url
    else:
        fir_url = get_fir_url(ipa_path, app_bundleid)
    return fir_url


# 步骤五  发送钉钉消息
def send_message(fir_url, git_branch, server_info, is_send_ding, ding_send_texts, app_name, app_version, app_bundleid, publish_appstore, project_path, logo_path):
    title = get_title(server_info, app_name, app_version)

    if publish_appstore == 1:
        send_store_message(title, git_branch)
    else:
        send_dev_message(fir_url, git_branch, ding_send_texts, title, app_bundleid, project_path, is_send_ding, logo_path)


def main():
    #####################################################################
    ##############################启动参数################################
    #####################################################################
    print('参数一服务器:(TEST, PRE_TEST, RELEASE)')
    print('参数二分支描述:(1: master, 2: dev...)')
    print('参数三是否发送钉钉消息:(YES, NO)')
    print('参数四钉钉消息内容')
    
    publish_appstore = 0

    git_branch = 'dev'
    is_send_ding = 'NO'
    is_upload = 'YES'
    ding_send_texts = []
    is_use_default_plist = 'YES'
    
    for index, item in enumerate(sys.argv):
        if index == 1:
            server_info = item
        elif index == 2:
            git_branch = item
        elif index == 3:
            is_send_ding = item
        elif index == 4:
            is_upload = item
        elif index == 5:
            is_use_default_plist = item
        else:
            if index != 0:
                ding_send_texts.append(item)


    #####################################################################
    #####################################################################
    #####################################################################

    # 获取工作目录 1.当前脚本目录 2.项目目录 3.pbxproj文件路径
    current_path, project_path, pbxproj_path, info_plist_path, logo_path, entitlements_path = get_project_path()

    # 获取工程文件中的证书配置信息  0 adhoc  1 appstore
    configuration = 'Release'
    plist_name = ['adhoc.plist', 'store.plist'][publish_appstore == 1]
    if is_use_default_plist == 'NO':
        plist_name = other_sign_plist

    project_team, profile_name, app_bundleid, app_origin_teamID, code_sign_teamID = get_project_info(project_path, pbxproj_path, plist_name)
    if is_use_default_plist == 'NO':
        code_sign_identity = other_sign_identity

    # 获取APP信息 1.APP 名字 2.APP版本号
    app_name, app_version, app_build_version = get_app_info(info_plist_path, pbxproj_path)

    # 获取当前scheme
    project_scheme = get_scheme()

    # 选择打包类型
    if server_info == 'FTP':
        upload_to_ftp(project_path, project_scheme, git_branch, app_name, app_version)
        return
    else:
        server_type, publish_appstore = get_publish_info(server_info)

    # 替换服务器URL
    replace_server(pbxproj_path, server_type, is_use_default_plist, entitlements_path, code_sign_teamID)


    #####################################################################
    #####################################################################

    # 步骤一  清理项目缓存及ipa   创建新build目录
    clean_project_build(project_path)

    # pod更新
    pod_update(project_path)

    # 步骤二 构建版本
    build_workspace(project_path, project_scheme, configuration, project_team, profile_name)

    # 步骤三 生成配置ipa包
    ipa_path = build_ipa(project_path, plist_name, project_scheme)

    # 步骤四  上传fir
    fir_url = upload_ipa(ipa_path, app_bundleid, publish_appstore, is_upload)

    # 步骤五  发送钉钉消息branch
    send_message(fir_url, git_branch, server_info, is_send_ding, ding_send_texts, app_name, app_version, app_bundleid, publish_appstore, project_path, logo_path)

    # 上传dysm文件
    upload_dsym(project_path, app_version, app_build_version, app_bundleid)

    # 服务器参数替换回来
    replace_back_server(pbxproj_path, server_type, is_use_default_plist, entitlements_path, app_origin_teamID)


if __name__ == '__main__':
    main()
