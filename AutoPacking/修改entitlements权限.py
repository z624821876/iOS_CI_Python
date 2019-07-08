import shutil
import os
import sys
from pbxproj import *


if __name__ == '__main__':

    workspace_path = sys.argv[1]
    print(workspace_path)
    current_path = os.path.dirname(os.path.realpath(__file__))
    print(current_path)
    # 1. 修改 project.pbxproj
    pbx_path = os.path.join(workspace_path, r'ALAFanBei/ALAFanBei.xcodeproj/project.pbxproj')
    # pbx_path = '/Users/aladin/.jenkins/workspace/51FanBeiTest/ALAFanBei/ALAFanBei.xcodeproj/project.pbxproj'
    print(pbx_path)
    project = XcodeProject.load(pbx_path)
    # project.get_keys()
    # print(project['objects'].get_sections())
    pbxproject_list = project['objects'].get_objects_in_section('PBXProject')
    for pbxproject in pbxproject_list:
        targets = pbxproject['attributes']['TargetAttributes']
        for key in targets.get_keys():
            SystemCapabilities = targets[key]['SystemCapabilities']
            if SystemCapabilities:
                SystemCapabilities['com.apple.AccessWiFi']['enabled'] = 0
                SystemCapabilities['com.apple.Push']['enabled'] = 0
    project.save(pbx_path)
    print(pbx_path)

    # 2. 替换.entitlements
    file_path = os.path.join(current_path, r'ALAFanBei.entitlements')
    print(file_path)
    new_path = os.path.join(workspace_path, r'ALAFanBei/ALAFanBei/Resources/ALAFanBei.entitlements')
    print(new_path)
    path = shutil.copyfile(file_path, new_path)
