#encoding:gbk
'''
溢价率乖离率策略调仓
#2024-02-25			TOTAL_POSTION=15000测试运行
#2024-03-01			TOTAL_POSTION=100000测试运行
####2024-03-02			改为单账户满仓逻辑。。。。03-04 先改回TOTAL_POSTION=100000测试运行
# 2024-05-07 	改为单账户满仓运行
# 2024-05-08 	用sell_df和buy_df的volume来判断是否完成全部调仓
# 				目前用是否完成volume买入来判断是否完成调仓，需基于满仓操作，否则还需判断是否卖出volume全部完成

'''
import pandas as pd
from datetime import datetime,date
import os
import time

#账户
MyAccount = '8881522601'

homedir = os.path.expanduser('~')
pythondir = os.path.join(homedir,'Trading')
DATA_DIR = os.path.join(pythondir, "Data")

#策略篮子文件
STRATEGY_FILE = os.path.join(DATA_DIR,"StrategyBascket")

#策略名称
STRATEGY_CONV_BIAS = 'CONV_BIAS' 

#策略总仓位，需保证账户总资产大于此值，满仓运行时忽略
TOTAL_POSTION = 400000

#撤单时间间隔，超过此时间未成交则撤单重报
WITHDRAW_SECS = 20

START_TIME = ' 14:53:00'

#保存交易状态的类
class a():
	pass
A = a() 
#撤销委托标志，用于判断本次调用是否有委托撤销，如果有，本周期不下买卖单，避免可用数量不足错误
A.order_canceled = 0
#定义不是本策略买入，无需卖出的标的
A.exlcude_code = pd.Series(['204001.SH'])

#2024-05-08全部调仓完成标志
A.done = 0

class StrategyBasket:

	def __init__(self, account,strategy_file,strategy_name,hold_number = 5):
		self.initiated = 0
		self.account = account
		self.strategy_file = strategy_file
		self.strategy_name = strategy_name
		self.hold_number = hold_number
		self.target_amount = 0                               #总目标仓位
		self.cash = 0
		self.sell_df = pd.DataFrame()
		self.buy_df = pd.DataFrame()

	# 初始化买入卖出篮子到buy_df sell_df,只需要调用一次。后续调仓逻辑在QMT runtime中完成
	# total_asset为账户总市值（满仓但策略运行），如果为TOTAL_POSTION则按照固定金额测试运行
	def init_basket(self,total_asset=TOTAL_POSTION):

		# 读入当日策略文件的'strategy' sheet
		self.target_df = pd.read_excel(self.strategy_file, sheet_name=self.strategy_name)  
		'''在主程序运行中获得账户信息
		#获取总资产
		acct = get_trade_detail_data(self.account,'stock', 'account')

		if len(acct) == 0:
			print(self.account, '账号未登录 停止委托')
			return

		for dt in acct:
			self.target_amount += dt.m_dBalance
			self.cash += dt.m_dAvailable

		print('cash:',self.cash)
		'''
		#可以设置测试金额15000RMB，为账户total_asset即全仓但策略运行
		self.target_amount = total_asset
		#单只持有金额
		self.single_amount = self.target_amount/self.hold_number
		

		#获取当前策略持仓：
		self.current_postion = pd.DataFrame()

		positions = get_trade_detail_data(self.account, 'stock', 'position')
		i = 0
		for dt in positions:
			
			self.current_postion.loc[i,'code'] = dt.m_strInstrumentID+'.'+dt.m_strExchangeID
			self.current_postion.loc[i,'volume'] = dt.m_nVolume
			self.current_postion.loc[i,'value'] = dt.m_dInstrumentValue
			
			i += 1
		
		target_codes = self.target_df['code'].head(5).tolist()
		position_codes = self.current_postion['code'].tolist()

		# 卖出不在当日策略标的中的股票,按照持仓数量volume卖出
		sell_codes = [code for code in position_codes if code not in target_codes]
		self.sell_df =  self.current_postion[self.current_postion['code'].isin(sell_codes)]
		#ordered 记录下单时间戳
		#self.sell_df['ordered'] = 0
		#done 记录成交数量
		#self.sell_df['done'] = 0
		
		self.sell_df = self.sell_df.assign(ordered=0, done=0)

		# 买入不在当日持仓中的策略标的，按照金额value买入
		buy_codes = [code for code in target_codes if code not in position_codes]
		
		self.buy_df = pd.DataFrame({'code':buy_codes,
									'value':self.single_amount,
									'volume':0, 
									'ordered':0, 
									'done':0})
		
		'''用上面的写法避免警告
		self.buy_df['code'] = buy_codes
		#按照金额下单买入
		self.buy_df['value'] = self.single_amount
		self.buy_df['volume'] = 0
		self.buy_df['ordered'] = 0
		self.buy_df['done'] = 0
		'''
		#设置为已经初始化，只需要初始化一次
		self.initiated = 1
		
		#特定品种不卖出
		self.sell_df = self.sell_df[~self.sell_df['code'].isin(A.exlcude_code)]
		
		#去除卖出量为0的行（由于盘中可能已经脉冲卖出）
		self.sell_df = self.sell_df.loc[self.sell_df['volume'] != 0]
		

	# 根据持仓，调整买入卖出标的数量
	def rebalance(self,C):
		
		target_codes = self.target_df['code'].head(5).tolist()
		position_codes = self.current_postion['code'].tolist()
		
		tick = C.get_full_tick(target_codes)
		
		for code in target_codes:
			if code in position_codes:
				code_amount = self.current_postion.loc[self.current_postion['code'] == code, 'value'].values[0]
				print('rebalance code:',code,'  持仓：', code_amount)
				# 如果持仓金额大于目标金额，尝试卖出
				if code_amount > self.single_amount:
					sell_amount = code_amount - self.single_amount
					
					#只有大于10张时需要卖出
					code_price = tick[code]['lastPrice']
					print('rebalance sell:',sell_amount,'price:',code_price)
					
					if sell_amount > 10*code_price:
						sell_volume = (sell_amount//(code_price*10))*10
						new_row = {'code':code,'value':sell_amount,'volume':sell_volume,'ordered':0,'done':0}
						self.sell_df = self.sell_df.append(new_row, ignore_index=True)
				# 如果持仓金额小于目标金额，尝试买入
				else:
					buy_amount = self.single_amount - code_amount
					
					#只有大于10张时需要买入
					code_price = tick[code]['lastPrice']
					print('rebalance buy:',buy_amount, 'price:',code_price)
					if buy_amount > 10*code_price:
						buy_volume = (buy_amount//(code_price*10))*10
						new_row = {'code':code,'value':buy_amount,'volume':buy_volume,'ordered':0,'done':0}
						self.buy_df = self.buy_df.append(new_row, ignore_index=True)
						
			#2024-05-07 买入的volume赋值，用来判断是否完成全部买入
			else:
				code_price = tick[code]['lastPrice']
				buy_volume = (self.single_amount//(code_price*10))*10
				self.buy_df.loc[self.buy_df['code'] == code, 'volume'] = buy_volume
				
		#确保code列为字符（df为空时可能会出现浮点类型）
		basket.buy_df['code'] = basket.buy_df['code'].astype(str)
		basket.sell_df['code'] = basket.sell_df['code'].astype(str)
		
		#basket.sell_df
		
#初始化篮子对象
dt = date.today()
s_filename = STRATEGY_FILE + str(dt) + '.xlsx'
basket = StrategyBasket(MyAccount,s_filename,STRATEGY_CONV_BIAS,5)

def init(C):
	
	dt = datetime.now()
	dt_str = dt.strftime("%Y-%m-%d")
	time_str = dt_str + START_TIME 
	

	C.run_time("f", "5nSecond", time_str)

def f(C):
	
	#本次运行时间字符串
	now = datetime.now()
	now_timestr = now.strftime("%H%M%S")
	print("\n in run time",str(now))
	
		#委托和撤单的时间戳
	t0 = time.time()
	#本轮时间戳，用于下一轮判断是否最新一轮的成交，只按照最新一轮的成交更新剩余需要委托数量
	#basket.t0 = t0

	#获取当前可用资金，动态，包含已卖出成交释放的可用资金
	acct = get_trade_detail_data(basket.account,'stock', 'account')
	
	#可用现金总是保持最新
	basket.cash = 0 
	#总资产只在初始化篮子时使用一次
	total_asset = 0
	
	for dt in acct:
		basket.cash += dt.m_dAvailable
		total_asset	+= dt.m_dBalance
		
	print('总资产:',total_asset)
	print('可用资金:',basket.cash)
	
			#初始化篮子
	if basket.initiated == 0:
		#初始化篮子
		
		#########满仓单账户运行
		#2024-05-07按照进入时点总资产的99.5%运行，避免卖出滑点可能导致可用资金不足无法买入委托
		total_asset = total_asset*0.995
		basket.init_basket(total_asset)
		
		#########2024-05-07 停止 按照TOTAL_POSTION限额运行
		#basket.init_basket()
		
		#基于持仓，调仓并更新买入和卖出标的
		basket.rebalance(C)
	
	#总仓位按照target_amount,而非可用资金. 单个策略全仓运行时应该去掉
	#if basket.cash > basket.target_amount:
	#	basket.cash = basket.target_amount
	
	print('buy:',basket.buy_df)
	print('sell:',basket.sell_df)
	
	#如果有未完成的买入，则标志置为0
	A.done = 1 
	
	for volume,done in zip(basket.buy_df['volume'], basket.buy_df['done']):
		
		if done < volume:
			A.done = 0
		
	print('\n A.done:',A.done)
	
	#2024-05-07 每次进入初始化已买入数量，用来判断是否已经全部买入
	basket.buy_df['done'] = 0
	
	#查询本策略的委托
	order_list = get_trade_detail_data(basket.account, 'stock', 'order',basket.strategy_name)
	
	for order in order_list:
		
		order_code = order.m_strInstrumentID + '.' + order.m_strExchangeID
		
		print('oder:',order.m_strOptName,': ',order_code)
		print('order.m_nVolumeTotal:',order.m_nVolumeTotal)
		
		#买入卖出需要分别处理：买入按照金额，卖出按照数量
		if order.m_strOptName == '限价买入': #and order_code in basket.buy_df['code']:
			
			#如果未到撤单时间不撤单，不更新篮子
			
			if (t0 - basket.buy_df.loc[basket.buy_df['code'] == order_code, 'ordered'] < WITHDRAW_SECS).any():
				continue
			
			#如果有成交，计入已成交计数
			if order.m_nOrderStatus in [55,56]:				#55：部分成交; 56：全部成交
				basket.buy_df.loc[basket.buy_df['code'] == order_code, 'done'] += order.m_nVolumeTraded
			
			#撤单处理，只有撤单时才需要更新剩余委托数量
			if order.m_nOrderStatus in [48,49,50,51,52,55,86,255]:
				print(f"超时撤单 停止等待 {order_code}")
				print('in cancel 委托剩余量:',order.m_nVolumeTotal,'成交金额：',order.m_dTradeAmount)
				
				cancel(order.m_strOrderSysID,basket.account,'stock',C)
				#设置撤单标志
				A.order_canceled = 1
				#撤单后，重置下单标志和更新剩余应该买入金额
				#重置下单标志
				basket.buy_df.loc[basket.buy_df['code'] == order_code, 'ordered'] = 0
				#委托买入金额减去成交金额，作为下一次买入委托的金额
				basket.buy_df.loc[basket.buy_df['code'] == order_code, 'value'] -= order.m_dTradeAmount
				
				
		if order.m_strOptName == '限价卖出': #and order_code in basket.sell_df['code']:
			
			#如果未到撤单时间不撤单，不更新篮子
			if (t0-basket.sell_df.loc[basket.sell_df['code'] == order_code, 'ordered'] < WITHDRAW_SECS).any():
				continue
			#撤单处理，只有撤单时才需要更新剩余委托数量
			if order.m_nOrderStatus in [48,49,50,51,52,55,86,255]:
				print(f"超时撤单 停止等待 {order_code}")
				print('in cancel 委托剩余量:',order.m_nVolumeTotal)
				cancel(order.m_strOrderSysID,basket.account,'stock',C)
				#设置撤单标志
				A.order_canceled = 1
				#撤单后，重置下单标志,更新剩余卖出数量
				basket.sell_df.loc[basket.sell_df['code'] == order_code, 'ordered'] = 0
				basket.sell_df.loc[basket.sell_df['code'] == order_code, 'volume'] = order.m_nVolumeTotal
	
	#检查撤单标志，如果有撤单，则不下新的买卖单，重置撤单标志，下一个周期下单
	if A.order_canceled == 1:
		print("有撤单，下个周期执行买入卖出操作")
		A.order_canceled = 0
		return
	
	#卖出下单，按照数量	
	for code,volume,ordered in zip(basket.sell_df['code'], basket.sell_df['volume'], basket.sell_df['ordered']):
		
		#用最新价卖出标的,volume保存本次应该下单数量，包括部分成交撤单后应重新委托的数量
		if(ordered == 0 and volume != 0):
			print('\n卖出委托: ', code, '数量：', volume)
			passorder(	24,					#卖出
						1101,				#股/手方式下单
						basket.account,		#账号 
						code,				#股票代码 
						5,					#最新价
						0,					#价格
						volume,				#数量
						basket.strategy_name,	#策略名称
						2,					#立即下单
						'',					#用户orderid
						C)
			#设置委托时间戳
			basket.sell_df.loc[basket.sell_df['code'] == code, 'ordered'] = t0
	
	#买入下单，按照金额	
	for code,value,ordered in zip(basket.buy_df['code'], basket.buy_df['value'],basket.buy_df['ordered']):
		
		#用最新价买入标的,value为本次需要买入的金额，包括部分成交撤单后应重新委托的金额
		if(ordered ==0 and value != 0 and basket.cash > value):
			print('\n买入委托: ', code, '金额：', value)
			passorder(	23,					#买入
						1102,				#金额方式下单
						basket.account,		#账号 
						code,				#股票代码 
						5,					#最新价
						0,					#价格
						value,				#数量
						basket.strategy_name,	#策略名称
						2,					#立即下单
						'',					#用户orderid
						C)
			#设置委托时间戳
			basket.buy_df.loc[basket.buy_df['code'] == code, 'ordered'] = t0
			#更新可用资金
			basket.cash -= value
		#判断是否是最后一只买入的标的，如果是，则用剩余可用资金买入
		elif(ordered ==0 and value != 0 and basket.cash < value):
			print('可用资金不足，可用：', basket.cash,'应买入：',code,'金额：',value)
			#df = basket.buy_df[basket.buy_df['code'] != code]
			#print('last df:',df)
			#如果所有其他买入标的都已下单，则用剩余可用资金买入当前标的
			#2024-04-09: 修改逻辑，如果
			'''
			if df['ordered'].ne(0).all():
				print('\n最后一只买入: ', code, '金额：', basket.cash)
				passorder(	23,					#买入
						1102,				#金额方式下单
						basket.account,		#账号 
						code,				#股票代码 
						5,					#最新价
						0,					#价格
						basket.cash,				#数量
						basket.strategy_name,	#策略名称
						2,					#立即下单
						'',					#用户orderid
						C)
				basket.buy_df.loc[basket.buy_df['code'] == code, 'ordered'] = t0
				#更新可用资金
				basket.cash -= value
			'''
