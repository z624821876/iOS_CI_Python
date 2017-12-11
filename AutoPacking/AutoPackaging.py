from DingHook import DingHook
import os
import re
import sys


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
def get_certificate_information(file_path, paking_type):
    with open(file_path, "r", encoding="UTF-8") as f:
        pbxproj = f.read()

    code_sign_identity = re.findall(r'CODE_SIGN_IDENTITY = "(.*?)\s\(.*?\)"', pbxproj)
    provisioning_profile_specifier = re.findall("PROVISIONING_PROFILE_SPECIFIER = (.*?);", pbxproj)

    if paking_type == 1:
        return code_sign_identity[0], provisioning_profile_specifier[0]
    else:
        return code_sign_identity[1], provisioning_profile_specifier[1]


# 获取当前scheme
def get_scheme():
    scheme_file = os.popen("cd ..;xcodebuild -list")
    scheme_string = scheme_file.read()
    scheme_file.close()

    string_location1 = scheme_string.find("\n", scheme_string.find("Schemes:\n        ") + len("Schemes:\n        "))
    scheme = scheme_string[scheme_string.find("Schemes:\n        ") + len("Schemes:\n        "):string_location1]
    return scheme


# 步骤一  清理项目缓存及ipa   创建新build目录
def clean_project_build(project_path):
    print("开始清理build缓存")
    os.system('cd %s;xcodebuild clean' % project_path)  # cd到路径，执行缓存清理 clean命令
    build_path = '%s/build' % project_path  # 配置build路径

    if os.path.exists(build_path):  # 如果build路径不为nil，移除build路径文件
        cleanCmd = "rm -r %s" % build_path
        os.system(cleanCmd)
    os.system('cd %s;mkdir build' % project_path)  # 在当前路径下，新建build文件目录


# 步骤二 构建版本
def build_workspace(project_path, project_scheme, configuration, project_teamName, profile_name):

    build_xcarchive = '%s/build/%s.xcarchive' % (project_path, project_scheme)

    print("构建版本配置： %s" % build_xcarchive)

    # 方式一 没有.xcworkspace执行
    # buildCmd = 'xcodebuild -project %s.xcodeproj -scheme %s -sdk iphoneos -configuration Release clean archive -archivePath %s  CODE_SIGN_IDENTITY="%s" PROVISIONING_PROFILE="%s"' % (project_scheme, project_scheme,build_xcarchive,project_teamName, project_uuid)
    # 方式一 有.xcworkspace执行
#    buildCmd = 'cd ..;xcodebuild -workspace %s.xcworkspace -scheme %s -sdk iphoneos -configuration %s clean archive -archivePath %s  CODE_SIGN_IDENTITY="%s" PROVISIONING_PROFILE="%s"' % (
#    project_scheme, project_scheme, configuration, build_xcarchive, project_teamName, project_uuid)
    buildCmd = 'cd ..;xcodebuild -workspace %s.xcworkspace -scheme %s -sdk iphoneos -configuration %s clean archive -archivePath %s  CODE_SIGN_IDENTITY="%s" PROVISIONING_PROFILE_SPECIFIER="%s"' % (
    project_scheme, project_scheme, configuration, build_xcarchive, project_teamName, profile_name)

    print("构建版本配置3： %s" % buildCmd)
    os.system(buildCmd)


# 步骤三 生成配置ipa包
def build_ipa(project_path, option_plist, project_scheme, filename_ipa):
    build_path = '%s/build' % project_path
    if os.path.exists(build_path):
        signCmd = 'xcodebuild -exportArchive -archivePath %s/%s.xcarchive -exportOptionsPlist %s -exportPath %s' % (build_path, project_scheme, option_plist, build_path)
        print(signCmd)
        os.system(signCmd)
        return filename_ipa
    else:
        print("没有找到app文件")
        return ''


# 步骤四  上传fir
def upload_ipa(project_path, ipa_name, fir_token, branch):
    ipa_path = os.path.join(project_path, "build", ipa_name)
    print("准备上传ipa %s " % ipa_path)
    short_path = None
    if branch == 1:
        short_path = "matermastermaster"
    else:
        short_path = "devdevdev"
    cmd = "fir publish %s --token=%s --short=%s -Q" % (ipa_path, fir_token, short_path)
    os.system(cmd)
    complete_path = "https://fir.im/" + short_path
    return complete_path


# 步骤五  发送钉钉消息
def send_message(fir_url, branch):
    title = None
    if branch == 1:
        title = "Master打包上传成功"
    else:
        title = "dev打包上传成功"

    print("准备发送钉钉消息")
    dh = DingHook()
    dh.post_qrCode(title=title, text=title, messageurl=fir_url)


def main():
    #####################################################################
    #####################################################################
    # 配置信息
    # 选择打包方式
    print("参数一打包的方式(1: dev, 2: adhoc, 3: appStore)")
    print("参数二(fir token)")
    print("参数三分支:(1: master, 2: dev)")
    paking_type = 2
    fir_token = "fir token 需要修改"
    branch = 2
    for index, item in enumerate(sys.argv):
        if index == 1:
            paking_type = int(item)
        elif index == 2:
            fir_token = item
        elif index == 3:
            branch = int(item)

    # 获取当前工程目录
    # __file__ 当前文件
    # os.path.realpath 获取文件真实路径
    # os.path.dirname 获取目录
    current_path = os.path.dirname(os.path.realpath(__file__))
    os.chdir(current_path)
    upper_path = os.path.dirname(current_path)
    # 删除空格
    project_path = upper_path.strip()

    # 工程文件
    xcodeproj_path = upper_path + "/%s.xcodeproj" % os.path.basename(upper_path)
    pbxproj_path = os.path.join(xcodeproj_path, "project.pbxproj")
    # 获取工程文件中的证书配置信息

    project_teamName, profile_name = get_certificate_information(pbxproj_path, paking_type)
    plist_path = None
    configuration = None

    # 需要放置相同名称的plist文件到脚本文件夹中
    if paking_type == 1:
        configuration = "Debug"
        plist_path = os.path.join(current_path, "dev.plist")
    else:
        configuration = "Release"
        plist_path = os.path.join(current_path, "adhoc.plist")

    # 获取当前scheme
    project_scheme = get_scheme()

    # 更新创建plist文件
    filename_ipa = '%s.ipa' % project_scheme
    #####################################################################
    #####################################################################

    # 步骤一  清理项目缓存及ipa   创建新build目录
    clean_project_build(project_path)

    # 步骤二 构建版本
    build_workspace(project_path, project_scheme, configuration, project_teamName, profile_name)

    # 步骤三 生成配置ipa包
    build_ipa(project_path, plist_path, project_scheme, filename_ipa)

    # 步骤四  上传fir
    fir_url = upload_ipa(project_path, filename_ipa, fir_token, branch)

    # 步骤五  发送钉钉消息
    send_message(fir_url, branch)


if __name__ == '__main__':
    main()
