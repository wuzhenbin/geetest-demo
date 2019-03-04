from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By

import time
import re
import io
import urllib.request
import cv2
import os
import random
from functools import reduce

from PIL import Image

chrome_options = Options()
chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")


class Crack():
    def __init__(self):
        self.url = 'http://localhost:5000/'
        self.driver = webdriver.Chrome(options=chrome_options)
        self.wait = WebDriverWait(self.driver, 10)
        self.driver.get(self.url)

    def get_slider(self):
        """
        获取滑块
        :return: 滑块对象
        """
        while True:
            try:
                slider = self.driver.find_element_by_xpath("//div[@class='gt_slider_knob gt_show']")
                break
            except:
                time.sleep(0.5)
        return slider

    def get_img_item(self,item):
        # 在html里面解析出小图片的url地址，还有长高的数值
        attr = item.get_attribute('style')
        pattern = "background-image: url\(\"(.*)\"\); background-position: (.*)px (.*)px;"
        res = re.findall(pattern,attr)

        imageurl = res[0][0]
        return {
            'x': int(res[0][1]),
            'y': int(res[0][2]),
            'imageurl': imageurl
        }

    def get_merge_image(self,filename,location_list):
        '''
        根据位置对图片进行合并还原
        :filename:图片
        :location_list:图片位置
        '''
        # 二进制读取方式
        im = Image.open(filename)
        # im.show()
     
        im_list_upper=[]
        im_list_down=[]
        
        for item in location_list:
            # y只有2个值 因为图片是由 2排图片组合成的
            '''
            x的序列 1 13 25 37 49 ..301
            y -58
            '''
            if item['y']==-58:
                crop_item = im.crop((abs(item['x']),58,abs(item['x'])+10,116))
                im_list_upper.append(crop_item)

            if item['y']==0:
                crop_item = im.crop((abs(item['x']),0,abs(item['x'])+10,58))
                im_list_down.append(crop_item)

        
        # 正确拼图大小为260*116
        new_im = Image.new('RGB', (260,116))
        
        # 从0开始往右拼图
        x_offset = 0
        for im in im_list_upper:
            new_im.paste(im, (x_offset,0))
            x_offset += im.size[0]
     
        x_offset = 0
        for im in im_list_down:
            new_im.paste(im, (x_offset,58))
            x_offset += im.size[0]
     
        return new_im

    def get_image(self,xpath_select_str):
        # 找到图片所在的div
        background_images = self.driver.find_elements_by_xpath(xpath_select_str)
        location_list=[]
     
        location_list = [self.get_img_item(item) for item in background_images]
        imageurl = location_list[0]['imageurl'].replace("webp","jpg")
        # 向内存中写入图片二进制流 
        jpgfile = io.BytesIO(urllib.request.urlopen(imageurl).read())

        # 重新合并图片 
        image = self.get_merge_image(jpgfile,location_list)
        return image

    def move_to_gap(self, slider, track, distance):
        """
        拖动滑块到缺口处
        :param slider: 滑块
        :param track: 轨迹
        :return:
        """
        # 找到滑动的圆球 点击元素 
        ActionChains(self.driver).click_and_hold(slider).perform()
        left_step = reduce(lambda x,y:x+y, track) - distance

        while track:
            x = random.choice(track)
            ActionChains(self.driver).move_by_offset(xoffset=x, yoffset=0).perform()
            track.remove(x)
            time.sleep(random.randint(6, 10) / 2000)   

        time.sleep(0.5)
        '''
        序列完了之后可能还会多出几步，我们把多出的几步往回走
        '''
        if left_step >0:
            for i in range(1,left_step+1):
                ActionChains(self.driver).move_by_offset(xoffset=-1, yoffset=0).perform()
                time.sleep(random.randint(6, 10) / 100)
                
        ActionChains(self.driver).release().perform()
    
    def save_miss_block(self):
        # 找到图片所在的div
        background_images = self.driver.find_elements_by_xpath("//div[@class='gt_slice gt_show']")
        if len(background_images) > 0:
            attr = background_images[0].get_attribute('style')
            pattern = "background-image: url\(\"(.*)\"\);"
            res = re.findall(pattern,attr)
            pngfile = io.BytesIO(urllib.request.urlopen(res[0]).read())
            im = Image.open(pngfile)
            im.save('miss_block.png')
            return True

        return False

    def find_pic_loc(self, target, template): 
        ''' 
            找出图像中最佳匹配位置 
            target: 目标即背景图 
            template: 模板即需要找到的图 
            :return: 返回最佳匹配及其最差匹配和对应的坐标 

            使用cv2库，先读取背景图，然后夜视化处理（消除噪点），然后读取模板图片，
            使用cv2自带图片识别找到模板在背景图中的位置，使用minMaxLoc提取出最佳匹配的最大值和最小值，
            返回一个数组形如(-0.3,0.95,(121,54),(45,543))元组四个元素，分别是最小匹配概率、最大匹配概率，
            最小匹配概率对应坐标，最大匹配概率对应坐标。

            我们需要的是最大匹配概率坐标，对应的分别是x和y坐标，但是这个不一定，有些时候可能是最小匹配概率坐标，
            最好是根据概率的绝对值大小来比较。

            滑块验证较为核心的两步，第一步是找出缺口距离，第二步是生成轨迹并滑动，较为复杂的情况下还要考虑初始模板图片在背景图中的坐标，以及模板图片透明边缘的宽度，这些都是影响轨迹的因素。
        '''
        target_rgb = cv2.imread(target) 
        target_gray = cv2.cvtColor(target_rgb, cv2.COLOR_BGR2GRAY) 
        template_rgb = cv2.imread(template, 0) 
        res = cv2.matchTemplate(target_gray, template_rgb, cv2.TM_CCOEFF_NORMED) 
        value = cv2.minMaxLoc(res)
        # 这里测试最准确的值是第[2]个的x坐标
        return value[2][0]

    def get_track(self, distance):
        """
        拿到移动轨迹，模仿人的滑动行为，先匀加速后均减速
        匀变速运动基本公式：
        ①：v=v0+at
        ②：s=v0t+½at²
        ③：v²-v0²=2as

        根据偏移量获取移动轨迹
        :param distance: 偏移量
        :return: 移动轨迹
        """
        # 移动轨迹
        track = []
        # 当前位移
        current = 0
        # 减速阈值
        mid = distance * 4 / 5
        # 计算间隔
        t = 0.2
        # 初速度
        v = 0
        
        while current < distance:
            if current < mid:
                # 加速度为正
                a = 7
            else:   
                # 加速度为负
                a = -7
            # 初速度v0
            v0 = v
            # 当前速度v = v0 + at
            v = v0 + a * t
            # 移动距离x = v0t + 1/2 * a * t^2
            move = v0 * t + 1 / 2 * a * t * t
            # 当前位移
            current += move
            # 加入轨迹
            track.append(round(move))

        return track


if __name__ == '__main__':
    crack = Crack()
    # 带缺口的背景图
    crack.wait.until(lambda the_driver: the_driver.find_element_by_xpath("//div[@class='gt_cut_bg gt_show']").is_displayed())
    img_target = crack.get_image("//div[@class='gt_cut_bg gt_show']/div[@class='gt_cut_bg_slice']")
    img_target.save('target_bg.jpg')

    # 保存缺块图片
    crack.save_miss_block()

    # 获取缺块在原图中的位置
    pic_loc = crack.find_pic_loc('target_bg.jpg','miss_block.png')

    track = crack.get_track(pic_loc)
    slider = crack.get_slider()
    crack.move_to_gap(slider, track, pic_loc)

    # 删除图片
    os.remove('miss_block.png')
    os.remove('target_bg.jpg')

