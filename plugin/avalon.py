# -*- coding:utf-8 -*-

import logging
import random
import re
import threading
import time
import os
import codecs

__author__ = 'sweet'

pluginRoot = os.path.split(os.path.realpath(__file__))[0]

class PlayerInfo(object):
    def __init__(self):
        self.uin = ''  # 用户唯一标示
        self.id = 0  # 用户编号
        self.name = ''  # 用户昵称
        self.isOut = False  # 是否出局
        self.identity = -1  # 身份
        self.identityList = ["空身份", "梅林", "派西维尔", "忠臣", "莫甘娜", "刺客", "奥伯伦", "爪牙"]  # 身份列表

class MsgDto(object):
    __slots__ = (
        'poll_type', 'from_uin', 'send_uin', 'msg_type', 'reply_ip', 'to_uin', 'content', 'raw_content')

    def __init__(self):
        self.from_uin = ''  # 群的uin
        self.send_uin = ''  # 发消息人的uin
        self.to_uin = ''
        self.content = ''


class StatusHandler(object):
    def __init__(self):
        self.status = 'undefined'

    def handle(self, game, msgDto):
        return False  # 退出


class StartStatus(StatusHandler):
    """
    <初始化阶段>
    """

    def __init__(self):
        super(StatusHandler, self).__init__()
        self.status = 'StartStatus'

    def handle(self, game, msgDto):
        content = msgDto.content
        matches = re.match(ur'.*阿瓦隆((\d+)人局)', content)
        if matches:
            playCount = -1
            if matches.group(2):
                if int(matches.group(2)) < 5 or int(matches.group(2)) > 7:
                    game.writePublic(u"目前只支持5-7人局呃。。")
                    return False
                playCount = int(matches.group(2))  # 至少5个人
            game.writePublic(u"玩游戏啦：阿瓦隆 %d 人局，想玩的快快加入~(输入“我要参加“加入游戏)" % playCount)
            game.statusHandle = ReadyStatus(game, playCount)
            return True
        return False


class ReadyStatus(StatusHandler):
    """
    <准备阶段>
    公告游戏人数
    允许玩家加入游戏
    """

    def __init__(self, game, maxPlayerCount):
        super(StatusHandler, self).__init__()
        self.status = 'ReadyStatus'
        self.__game = game
        self.__maxPlayerCount = maxPlayerCount
        self.__startNotifyThread()

    def handle(self, game, msgDto):
        matchSuccess = re.match(ur'^\s*我要参加\s*$', msgDto.content)
        if not matchSuccess:
            return False
        playerInfo = PlayerInfo()
        playerInfo.uin = msgDto.send_uin
        playerInfo.name = game.uin2name(msgDto.send_uin)
        if playerInfo.uin in [x.uin for x in game.playerList]:
            return False
        game.addPlayer(playerInfo)
        game.writePublic(u"%s 加入游戏，当前人数 %d/%d" % (playerInfo.name, len(game.playerList), self.__maxPlayerCount))
        if len(game.playerList) >= self.__maxPlayerCount:
            return self.next()
        return False

    def __startNotifyThread(self, timeout=80):
        def process(statusHandle, game, timeout):
            while statusHandle == game.statusHandle and timeout > 0:
                time.sleep(1)
                timeout -= 1
                if timeout <= 0:
                    statusHandle.next()  # 开始游戏
                    return
                if timeout % 20 == 0:
                    game.writePublic(u"要玩游戏的快加入啦，剩余%s秒。" % (timeout))
                    continue
            return

        thread = threading.Thread(target=process, args=(self, self.__game, timeout))
        thread.start()

    def next(self):
        """
        进入下一阶段
        """
        lock = self.__game.lock
        lock.acquire()
        try:
            if self.__game.statusHandle == self:
                self.__game.statusHandle = AssignRolesStatus(self.__game)
            return True
        finally:
            lock.release()


class AssignRolesStatus(StatusHandler):
    """
    <分配角色阶段>
    初始化用户身份信息
    """

    def __init__(self, game):
        """
        :param playerCount: 游戏人数
        :return:
        """
        super(StatusHandler, self).__init__()
        self.status = 'AssignRolesStatus'
        self.__game = game
        self.__nextStatusHandle = None
        self.__assignRoles()

    def handle(self, game, msgDto):
        game.statusHandle = self.__nextStatusHandle
        return True

    def __assignRoles(self):
        game = self.__game
        playerCount = len(game.playerList)
        playerNames = '\n'.join(['[%s号]%s' % (x.id, x.name) for x in game.playerList])
        game.writePublic(u"[%s]本次游戏共 %d 人。玩家列表：\n%s\n\n我会私聊通知各玩家身份哦，记得查看!!~~" % (
            game.gameId, len(game.playerList), playerNames))
        # 获取身份序列
        identityList = self.__extractIdentity(playerCount)
        # 分配身份 1梅林2派西维尔36忠臣4莫甘娜5刺客7奥伯伦
        badGuy = []
        notOberon = []
        Merlin = []
        for x in game.playerList:
            if identityList[x.id-1] <= 5:
                x.identity = identityList[x.id-1]
                if identityList[x.id-1] == 5:
                    game._assasin = x
            elif identityList[x.id-1] == 6:
                x.identity = 3
            elif identityList[x.id-1] == 7:
                x.identity = 6
            else:
                game.writePrivate(x.uin, u'出错啦，快向群主反应吧。')
            if x.identity == 1 or x.identity == 4:
                Merlin.append(x)
            if x.identity >= 4:
                badGuy.append(x)
                if x.identity != 6:
                    notOberon.append(x)
        badGuyNames = '\n'.join(['[%s号]%s' % (x.id, x.name) for x in badGuy])
        notOberonNames = '\n'.join(['[%s号]%s' % (x.id, x.name) for x in notOberon])
        MerlinNames = '\n'.join(['[%s号]%s' % (x.id, x.name) for x in Merlin])
        goodWinCondi = u'任务成功3次，且梅林没被刺客刺杀'
        badWinCondi = u'任务失败3次，或刺客成功刺杀梅林'
        # 发送身份消息
        for x in game.playerList:
            if x.identity == 1:
                game.writePrivate(x.uin, u'[阿瓦隆]\n号码：%s号\n身份：%s\n能力：可以看到坏人，他们是\n%s\n胜利条件：%s' % (x.id, x.identityList[x.identity], badGuyNames, goodWinCondi))
            elif x.identity == 2:
                game.writePrivate(x.uin, u'[阿瓦隆]\n号码：%s号\n身份：%s\n能力：可以看到梅林，他们是\n%s\n但其中有一个是莫甘娜的幻影\n胜利条件：%s' % (x.id, x.identityList[x.identity], MerlinNames, goodWinCondi))
            elif x.identity == 3:
                game.writePrivate(x.uin, u'[阿瓦隆]\n号码：%s号\n身份：%s\n能力：决定游戏胜负的人物！\n胜利条件：%s' % (x.id, x.identityList[x.identity], goodWinCondi))
            elif x.identity == 4 or x.identity == 5:
                game.writePrivate(x.uin, u'[阿瓦隆]\n号码：%s号\n身份：%s\n能力：邪恶方的阵营有\n%s\n胜利条件：%s' % (x.id, x.identityList[x.identity], notOberonNames, badWinCondi))
            elif x.identity == 6:
                game.writePrivate(x.uin, u'[阿瓦隆]\n号码：%s号\n身份：%s\n能力：邪恶方还没有发现你这名队友\n胜利条件：%s' % (x.id, x.identityList[x.identity], badWinCondi))
            else:
                game.writePrivate(x.uin, u'出错啦，快向群主反应吧~')
        self.__nextStatusHandle = SpeechStatus(self.__game, False, True)
        return True
        '''
        game = self.__game
        playerCount = len(game.playerList)
        maxUndercover = len(game.playerList) // 3
        self.__undercoverCount = min(maxUndercover, self.__undercoverCount)
        if playerCount < 3 or self.__undercoverCount <= 0:
            game.writePublic("玩家过少，游戏结束")
            self.__nextStatusHandle = EndStatus()
            return True
        # 获取卧底词
        normalWord, specialWord = self.__extractWords()
        # 分配卧底身份
        for x in game.playerList:
            x.isUndercover = False
            x.word = normalWord
        while len([x for x in game.playerList if x.isUndercover]) < self.__undercoverCount:
            i = random.randint(0, len(game.playerList) - 1)
            game.playerList[i].isUndercover = True
            game.playerList[i].word = specialWord
        # 游戏信息
        playerNames = '\n'.join(['[%s号]%s' % (x.id, x.name) for x in game.playerList])
        game.writePublic(u"[%s]本次游戏共 %d 人，卧底 %d 人。玩家列表：\n%s\n\n我会私聊通知各玩家身份哦，记得查看!!~~" % (
            game.gameId, len(game.playerList), self.__undercoverCount, playerNames))
        # 私聊玩家，通知词语
        for x in game.playerList:
            game.writePrivate(x.uin, u'[%s]谁是卧底，您本局[%s]的词语是：%s' % (x.name,game.gameId, x.word))
        # 进入发言阶段
        self.__nextStatusHandle = SpeechStatus(self.__game)
        return True
        '''

    def __extractIdentity(self, playerCount):
        """
        抽取身份
        :return:
        """
        randomList = range(1, playerCount+1)
        random.shuffle(randomList)
        return randomList
        """
        with codecs.open(wodiConf, 'r', 'utf-8') as conf:
            lines = conf.readlines()
            lineNo = random.randint(0, len(lines) - 1)
            words = str(lines[lineNo]).replace('\n', '').split('----')
            if len(words) == 2:
                n = random.randint(0, 1)
                normalWord = words[n].strip()
                specialWord = words[1 - n].strip()
                return normalWord, specialWord
        return None, None
        """


class SpeechStatus(StatusHandler):
    """
    <发言阶段>
    玩家依次发言
    注意：回复“[xxx]执行任务”运行的是任务阶段，而不是投票决定是否通过这次组队的阶段
    """

    def __init__(self, game, final=False, isFirstTime=False):
        super(StatusHandler, self).__init__()
        self.status = 'SpeechStatus'
        self.__game = game
        self._isFirstTime = isFirstTime
        self._final = final
        self._teamNumber = [[0],[1],[2],[3],[4],[2,3,2,3,3],[2,3,4,3,4],[2,3,3,4,4]]   # 出任务的标准人数
        self._playerSet = {}
        self.__first()
        self.__startNotifyThread()

    def handle(self, game, msgDto):
        #注释部分为机器人控制发言，现在用的是玩家控制发言结束
        uin = msgDto.send_uin
        if uin not in self._playerSet:
            return False
        matches = re.match(ur'.*\[(\d+)\]执行任务', msgDto.content)
        if matches and not self._final:
            # 储存执行任务者信息
            teamNum = str(matches.group(1)) # 出任务者的号码，例如"134"
            team = []
            lst = game.playerList
            rightNumber = self._teamNumber[len(lst)][game._round-1]
            if len(teamNum) != rightNumber:
                game.writePublic(u"人数错误！应选择%s人执行任务。" % (rightNumber))
                return False
            for x in lst:
                for y in teamNum:
                    if str(x.id) == y:
                        team.append(x)
                        break
            teamNames = '\n'.join(['[%s号]%s' % (x.id, x.name) for x in team])
            # 写入txt
            f = open('avalon.txt','w')
            f.write('1\n')  # 1表示任务成功，0表示任务失败
            f.write(str(len(team))+'\n')    # 未执行任务人数
            f.write('0\n')  # 反对票数
            for x in team:
                f.write(x.name+'\n')    # 执行者信息
            f.close()
            return self.next(teamNames, "vote")
        matches = re.match(ur'.*刺杀((\d+)号)', msgDto.content)
        if matches and uin == game._assasin.uin:
            if matches.group(2):
                for x in game.playerList:
                    if x.identity == 1:
                        if x.id == int(matches.group(2)):
                            game.writePublic(u"邪恶阵营胜利！刺客成功刺杀梅林！")
                        else:
                            game.writePublic(u"正义方胜利！刺客没有刺杀梅林，真正的梅林是[%s号]" % (x.id))
                        break
                return self.next("", "kill")
        return False
        """
        uin = msgDto.send_uin
        content = msgDto.content
        if uin not in self._playerSet:
            return False
        if uin not in self._history:
            self._history[uin] = content
        # 发言结果
        if len(self._history) >= len(self._playerSet):
            lst = [(u'[%s号]: %s' % (self._playerSet[uin], value)) for uin, value in self._history.items()]
            playerReplys = '\n'.join(lst)
            game.writePublic(u"发言结束：\n" + playerReplys)
            return self.next()
        return False
        """

    def __first(self):
        game = self.__game
        lst = game.playerList
        for x in lst:
            self._playerSet[x.uin] = x.id
        if self._isFirstTime:
            i = random.randint(0, len(lst) - 1)
            playerInfo = lst[i]
            game.writePublic(u"第%s轮任务，请队长[%s号]%s组队并组织发言。\n回复“[xxx]执行任务”决定进行投票的人。\n（刺客可随时回复“刺杀x号”）" % (game._round, playerInfo.id, playerInfo.name))
        elif self._final:
            game.writePublic(u"任务成功3次！刺客请回复“刺杀x号”来刺杀梅林。")
        else:
            game.writePublic(u"第%s轮任务，请下一位队长组队并组织发言。\n回复“[xxx]执行任务”决定进行投票的人。\n（刺客可随时回复“刺杀x号”）" % (game._round))
        return

    def __startNotifyThread(self, timeout=1800):
        def process(statusHandle, game, timeout):
            while statusHandle == game.statusHandle and timeout > 0:
                time.sleep(10)
                timeout -= 10
                if timeout <= 0:
                    statusHandle.next()  # 进行下一阶段
                    return
                if timeout == 60:
                    game.writePublic(u"还没有发言的玩家快发言啦，剩余%s秒。" % (timeout))
                    continue
            return

        thread = threading.Thread(target=process, args=(self, self.__game, timeout))
        thread.start()

    def next(self, teamNames, status):
        """
        进入下一阶段
        """
        lock = self.__game.lock
        lock.acquire()
        try:
            if self.__game.statusHandle == self:
                if status == "vote":
                    self.__game.statusHandle = VoteStatus(self.__game, teamNames)
                elif status == "kill":
                    self.__game.statusHandle = EndStatus()
            return True
        finally:
            lock.release()


class VoteStatus(StatusHandler):
    """
    <投票阶段>
    玩家私聊机器人投票
    """

    def __init__(self, game, teamNames):
        super(StatusHandler, self).__init__()
        self.status = 'VoteStatus'
        self.__game = game
        #self._history = {}
        #self._score = {}
        self._result = ''   # 任务结果 1为成功 0为失败
        self._nCount = ''   # 反对票数
        self._teamNames = teamNames
        self.__first()
        self.__startNotifyThread()

    def handle(self, game, msgDto):
        #投票部分的代码在Pm.py文件中
        uin = msgDto.send_uin
        content = msgDto.content
        if uin not in self._playerSet:
            return False
        matches = re.match(ur'^\s*查看结果\s*$', content)
        if matches:
            game.writePublic(u"正在查询中。。。")
            f = open('avalon.txt','r')
            voteInfo = f.readlines()
            self._result = voteInfo[0][:-1]
            restNum = voteInfo[1][:-1]
            self._nCount = voteInfo[2][:-1]
            names = voteInfo[3:]
            f.close()
            if restNum != '0':
                game.writePublic(u"还有%s人没投票，抓紧时间呀~" % (restNum))
                return False
            return self.next()
        return False
        """
        if uin not in self._history:
            matches = re.match(ur'.*(\d+)号*', content)
            if matches:
                id = int(matches.group(1))
                self._history[uin] = content
                if id not in self._score:
                    self._score[id] = 1
                else:
                    self._score[id] += 1
        # 投票结束
        if len(self._history) >= len(self._playerSet):
            return self.next()
        return False
        """

    def __first(self):
        game = self.__game
        self._playerSet = set([x.uin for x in game.playerList if not x.isOut])
        game.writePublic(u"投票开始，请下列玩家私戳我进行投票：\n%s\n同意回复“y”，反对回复“n”。\n\n投完票的小伙伴请在群里冒个泡~回复“查看结果”进行下一步" % (self._teamNames))
        return

    def __startNotifyThread(self, timeout=300):
        def process(statusHandle, game, timeout):
            while statusHandle == game.statusHandle and timeout > 0:
                time.sleep(10)
                timeout -= 10
                if timeout <= 0:
                    statusHandle.next()  # 进行下一阶段
                    return
                if timeout == 60:
                    game.writePublic(u"快投票哇，剩余%s秒。" % (timeout))
                    continue
            return

        thread = threading.Thread(target=process, args=(self, self.__game, timeout))
        thread.start()

    def next(self):
        """
        进入下一阶段
        """
        lock = self.__game.lock
        lock.acquire()
        try:
            if self.__game.statusHandle == self:
                self.__game.statusHandle = VerdictStatus(self.__game, self._result, self._nCount)
            return True
        finally:
            lock.release()


class VerdictStatus(StatusHandler):
    """
    <裁决阶段>
    """

    def __init__(self, game, result, nCount):
        super(StatusHandler, self).__init__()
        self.status = 'VerdictStatus'
        self.__game = game
        self._result = result
        self._nCount = nCount
        self.__nextStatusHandle = None
        self.__first()

    def handle(self, game, msgDto):
        game.statusHandle = self.__nextStatusHandle
        return True

    def __first(self):
        game = self.__game
        if self._result == '1':
            game.writePublic(u'任务成功！')
            game._winTimes += 1
            if game._winTimes == 3:
                self.__nextStatusHandle = SpeechStatus(game, True)
                return True
        elif self._result == '0':
            game.writePublic(u'任务失败！有%s张反对票' % (self._nCount))
            if game._round - game._winTimes == 3:
                game.writePublic(u'任务失败3次！邪恶阵营胜利！')
                self.__nextStatusHandle = EndStatus()
                return True
        else:
            game.writePublic(u'出错啦QAQ')
        game._round += 1
        self.__nextStatusHandle = SpeechStatus(game)
        return True       
        """
        sortedScore = self.__getScore(game.playerList)
        msg = u'投票结果：\n'
        scoreList = '\t\n'.join([u'[%s号]: %s票' % (p.id, p.score) for p in sortedScore])
        outPlayer = sortedScore[0]
        p2 = sortedScore[1]
        # 平票
        if outPlayer.score == p2.score:
            game.writePublic(msg + scoreList + u'\n==== 平票！请继续发言 ====')
            self.__nextStatusHandle = SpeechStatus(game)
            return True
        # 玩家出局
        game.outPlayer(outPlayer.id)
        result = u'\n==== [%s号]%s 被投票出局 ====' % (outPlayer.id, outPlayer.name)
        game.writePublic(msg + scoreList + result)
        # 胜负判断
        undercoverCount = len([x for x in game.playerList if x.isUndercover])
        playerCount = len(game.playerList)
        if undercoverCount == 0:
            game.writePublic(u'==== 卧底出局，平民赢得胜利！！！ ====')
            self.__nextStatusHandle = EndStatus()
            return True
        elif playerCount == 2 or playerCount == undercoverCount:
            game.writePublic(u'==== 卧底获胜！！！ ====')
            self.__nextStatusHandle = EndStatus()
            return True
        self.__nextStatusHandle = SpeechStatus(game)
        return True
        """

    """
    def __getScore(self, playerList):
        keys = self._score.keys()
        for x in playerList:
            if x.id in keys:
                x.score = self._score[x.id]
            else:
                x.score = 0
        sortedScore = sorted(playerList, key=lambda x: x.score, reverse=True)
        return [x for x in sortedScore if x.score > 0]
    """


class EndStatus(StatusHandler):
    """
    <结束阶段>
    """

    def __init__(self):
        super(StatusHandler, self).__init__()
        self.status = 'EndStatus'

    def handle(self, game, msgDto):
        game.statusHandle = StartStatus()
        return False


class Game(object):
    def __init__(self, statusHandle, groupHandler):
        self.statusHandle = statusHandle
        self.gameId = str(int(time.time()))[-5:]
        self.__playerList = []
        self._output = groupHandler
        self._round = 1
        self._winTimes = 0
        self._assasin = ''
        self.lock = threading.Lock()

    @property
    def playerList(self):
        return tuple([x for x in self.__playerList if not x.isOut])

    @property
    def status(self):
        return self.statusHandle.status

    def addPlayer(self, playerInfo):
        playerInfo.id = len(self.__playerList) + 1
        self.__playerList.append(playerInfo)

    def outPlayer(self, id):
        """
        出局某玩家
        :param id: 玩家id
        :return:
        """
        for x in self.__playerList:
            if x.id == id:
                x.isOut = True
        pass

    def id2playerInfo(self, id):
        for x in self.playerList:
            if x.id == id:
                return x
        return None

    def writePublic(self, content):
        self._output.reply(content)
        time.sleep(0.5)
        pass

    def writePrivate(self, tuin, content):
        self._output.reply_sess(tuin, content)
        time.sleep(0.5)
        pass

    def uin2name(self, uin):
        """
        获取群成员信息，返回昵称
        :param uin:
        :return:str
        """
        return self._output.get_menber_info(uin)
        """
        lst = self._output.get_member_list()
        for x in lst:
            if str(x.uin) == str(uin):
                return x.nick
        return ""
        """

    def run(self, msgDto):
        isProcess = False
        while self.statusHandle.handle(self, msgDto):
            isProcess = True
            pass
        return isProcess


# ===========================================================================================


if __name__ == "__main__":
    import sys

    reload(sys)
    sys.setdefaultencoding("utf-8")
    logging.basicConfig(level=logging.DEBUG)
    output = logging
    output.reply = logging.info
    output.reply_sess = lambda uin, msg: logging.info(msg)
    output.get_member_list = lambda: []

    """
    # 开始5人局
    status = StartStatus()
    game = Game(status, output)
    msgDto = MsgDto()
    msgDto.content = u'!game 开始谁是卧底5人局2卧底'
    game.run(msgDto)

    # 报名
    game.run(MsgDto())
    msgDto1 = MsgDto()
    msgDto1.send_uin = '1'
    msgDto1.content = u'我要参加'
    game.run(msgDto1)
    msgDto2 = MsgDto()
    msgDto2.send_uin = '2'
    msgDto2.content = u'我要参加'
    game.run(msgDto2)
    msgDto3 = MsgDto()
    msgDto3.send_uin = '3'
    msgDto3.content = u'我要参加'
    game.run(msgDto3)
    msgDto4 = MsgDto()
    msgDto4.send_uin = '4'
    msgDto4.content = u'我要参加'
    game.run(msgDto4)
    msgDto5 = MsgDto()
    msgDto5.send_uin = '5'
    msgDto5.content = u'我要参加'
    game.run(msgDto5)

    # 发言
    msgDto1.content = u'发言1'
    game.run(msgDto1)
    msgDto2.content = u'发言2'
    game.run(msgDto2)
    msgDto3.content = u'发言3'
    game.run(msgDto3)
    msgDto4.content = u'发言4'
    game.run(msgDto4)
    msgDto5.content = u'发言5'
    game.run(msgDto5)

    # 投票
    msgDto1.content = u'1号'
    game.run(msgDto1)
    msgDto2.content = u'我投1号'
    game.run(msgDto2)
    msgDto3.content = u'2号是卧底'
    game.run(msgDto3)
    msgDto4.content = u'1'
    game.run(msgDto4)
    msgDto5.content = u'3号'
    game.run(msgDto5)
    threading.Event().set()

    # time.sleep(3)
    """
