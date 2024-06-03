#encoding:gbk
'''
����ʹ����ʲ��Ե���
#2024-02-25			TOTAL_POSTION=15000��������
#2024-03-01			TOTAL_POSTION=100000��������
####2024-03-02			��Ϊ���˻������߼���������03-04 �ȸĻ�TOTAL_POSTION=100000��������
# 2024-05-07 	��Ϊ���˻���������
# 2024-05-08 	��sell_df��buy_df��volume���ж��Ƿ����ȫ������
# 				Ŀǰ���Ƿ����volume�������ж��Ƿ���ɵ��֣���������ֲ������������ж��Ƿ�����volumeȫ�����

'''
import pandas as pd
from datetime import datetime,date
import os
import time

#�˻�
MyAccount = '8881522601'

homedir = os.path.expanduser('~')
pythondir = os.path.join(homedir,'Trading')
DATA_DIR = os.path.join(pythondir, "Data")

#���������ļ�
STRATEGY_FILE = os.path.join(DATA_DIR,"StrategyBascket")

#��������
STRATEGY_CONV_BIAS = 'CONV_BIAS' 

#�����ܲ�λ���豣֤�˻����ʲ����ڴ�ֵ����������ʱ����
TOTAL_POSTION = 400000

#����ʱ������������ʱ��δ�ɽ��򳷵��ر�
WITHDRAW_SECS = 20

START_TIME = ' 14:53:00'

#���潻��״̬����
class a():
	pass
A = a() 
#����ί�б�־�������жϱ��ε����Ƿ���ί�г���������У������ڲ�����������������������������
A.order_canceled = 0
#���岻�Ǳ��������룬���������ı��
A.exlcude_code = pd.Series(['204001.SH'])

#2024-05-08ȫ��������ɱ�־
A.done = 0

class StrategyBasket:

	def __init__(self, account,strategy_file,strategy_name,hold_number = 5):
		self.initiated = 0
		self.account = account
		self.strategy_file = strategy_file
		self.strategy_name = strategy_name
		self.hold_number = hold_number
		self.target_amount = 0                               #��Ŀ���λ
		self.cash = 0
		self.sell_df = pd.DataFrame()
		self.buy_df = pd.DataFrame()

	# ��ʼ�������������ӵ�buy_df sell_df,ֻ��Ҫ����һ�Ρ����������߼���QMT runtime�����
	# total_assetΪ�˻�����ֵ�����ֵ��������У������ΪTOTAL_POSTION���չ̶�����������
	def init_basket(self,total_asset=TOTAL_POSTION):

		# ���뵱�ղ����ļ���'strategy' sheet
		self.target_df = pd.read_excel(self.strategy_file, sheet_name=self.strategy_name)  
		'''�������������л���˻���Ϣ
		#��ȡ���ʲ�
		acct = get_trade_detail_data(self.account,'stock', 'account')

		if len(acct) == 0:
			print(self.account, '�˺�δ��¼ ֹͣί��')
			return

		for dt in acct:
			self.target_amount += dt.m_dBalance
			self.cash += dt.m_dAvailable

		print('cash:',self.cash)
		'''
		#�������ò��Խ��15000RMB��Ϊ�˻�total_asset��ȫ�ֵ���������
		self.target_amount = total_asset
		#��ֻ���н��
		self.single_amount = self.target_amount/self.hold_number
		

		#��ȡ��ǰ���Գֲ֣�
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

		# �������ڵ��ղ��Ա���еĹ�Ʊ,���ճֲ�����volume����
		sell_codes = [code for code in position_codes if code not in target_codes]
		self.sell_df =  self.current_postion[self.current_postion['code'].isin(sell_codes)]
		#ordered ��¼�µ�ʱ���
		#self.sell_df['ordered'] = 0
		#done ��¼�ɽ�����
		#self.sell_df['done'] = 0
		
		self.sell_df = self.sell_df.assign(ordered=0, done=0)

		# ���벻�ڵ��ճֲ��еĲ��Ա�ģ����ս��value����
		buy_codes = [code for code in target_codes if code not in position_codes]
		
		self.buy_df = pd.DataFrame({'code':buy_codes,
									'value':self.single_amount,
									'volume':0, 
									'ordered':0, 
									'done':0})
		
		'''�������д�����⾯��
		self.buy_df['code'] = buy_codes
		#���ս���µ�����
		self.buy_df['value'] = self.single_amount
		self.buy_df['volume'] = 0
		self.buy_df['ordered'] = 0
		self.buy_df['done'] = 0
		'''
		#����Ϊ�Ѿ���ʼ����ֻ��Ҫ��ʼ��һ��
		self.initiated = 1
		
		#�ض�Ʒ�ֲ�����
		self.sell_df = self.sell_df[~self.sell_df['code'].isin(A.exlcude_code)]
		
		#ȥ��������Ϊ0���У��������п����Ѿ�����������
		self.sell_df = self.sell_df.loc[self.sell_df['volume'] != 0]
		

	# ���ݳֲ֣��������������������
	def rebalance(self,C):
		
		target_codes = self.target_df['code'].head(5).tolist()
		position_codes = self.current_postion['code'].tolist()
		
		tick = C.get_full_tick(target_codes)
		
		for code in target_codes:
			if code in position_codes:
				code_amount = self.current_postion.loc[self.current_postion['code'] == code, 'value'].values[0]
				print('rebalance code:',code,'  �ֲ֣�', code_amount)
				# ����ֲֽ�����Ŀ�����������
				if code_amount > self.single_amount:
					sell_amount = code_amount - self.single_amount
					
					#ֻ�д���10��ʱ��Ҫ����
					code_price = tick[code]['lastPrice']
					print('rebalance sell:',sell_amount,'price:',code_price)
					
					if sell_amount > 10*code_price:
						sell_volume = (sell_amount//(code_price*10))*10
						new_row = {'code':code,'value':sell_amount,'volume':sell_volume,'ordered':0,'done':0}
						self.sell_df = self.sell_df.append(new_row, ignore_index=True)
				# ����ֲֽ��С��Ŀ�����������
				else:
					buy_amount = self.single_amount - code_amount
					
					#ֻ�д���10��ʱ��Ҫ����
					code_price = tick[code]['lastPrice']
					print('rebalance buy:',buy_amount, 'price:',code_price)
					if buy_amount > 10*code_price:
						buy_volume = (buy_amount//(code_price*10))*10
						new_row = {'code':code,'value':buy_amount,'volume':buy_volume,'ordered':0,'done':0}
						self.buy_df = self.buy_df.append(new_row, ignore_index=True)
						
			#2024-05-07 �����volume��ֵ�������ж��Ƿ����ȫ������
			else:
				code_price = tick[code]['lastPrice']
				buy_volume = (self.single_amount//(code_price*10))*10
				self.buy_df.loc[self.buy_df['code'] == code, 'volume'] = buy_volume
				
		#ȷ��code��Ϊ�ַ���dfΪ��ʱ���ܻ���ָ������ͣ�
		basket.buy_df['code'] = basket.buy_df['code'].astype(str)
		basket.sell_df['code'] = basket.sell_df['code'].astype(str)
		
		#basket.sell_df
		
#��ʼ�����Ӷ���
dt = date.today()
s_filename = STRATEGY_FILE + str(dt) + '.xlsx'
basket = StrategyBasket(MyAccount,s_filename,STRATEGY_CONV_BIAS,5)

def init(C):
	
	dt = datetime.now()
	dt_str = dt.strftime("%Y-%m-%d")
	time_str = dt_str + START_TIME 
	

	C.run_time("f", "5nSecond", time_str)

def f(C):
	
	#��������ʱ���ַ���
	now = datetime.now()
	now_timestr = now.strftime("%H%M%S")
	print("\n in run time",str(now))
	
		#ί�кͳ�����ʱ���
	t0 = time.time()
	#����ʱ�����������һ���ж��Ƿ�����һ�ֵĳɽ���ֻ��������һ�ֵĳɽ�����ʣ����Ҫί������
	#basket.t0 = t0

	#��ȡ��ǰ�����ʽ𣬶�̬�������������ɽ��ͷŵĿ����ʽ�
	acct = get_trade_detail_data(basket.account,'stock', 'account')
	
	#�����ֽ����Ǳ�������
	basket.cash = 0 
	#���ʲ�ֻ�ڳ�ʼ������ʱʹ��һ��
	total_asset = 0
	
	for dt in acct:
		basket.cash += dt.m_dAvailable
		total_asset	+= dt.m_dBalance
		
	print('���ʲ�:',total_asset)
	print('�����ʽ�:',basket.cash)
	
			#��ʼ������
	if basket.initiated == 0:
		#��ʼ������
		
		#########���ֵ��˻�����
		#2024-05-07���ս���ʱ�����ʲ���99.5%���У���������������ܵ��¿����ʽ����޷�����ί��
		total_asset = total_asset*0.995
		basket.init_basket(total_asset)
		
		#########2024-05-07 ֹͣ ����TOTAL_POSTION�޶�����
		#basket.init_basket()
		
		#���ڳֲ֣����ֲ�����������������
		basket.rebalance(C)
	
	#�ܲ�λ����target_amount,���ǿ����ʽ�. ��������ȫ������ʱӦ��ȥ��
	#if basket.cash > basket.target_amount:
	#	basket.cash = basket.target_amount
	
	print('buy:',basket.buy_df)
	print('sell:',basket.sell_df)
	
	#�����δ��ɵ����룬���־��Ϊ0
	A.done = 1 
	
	for volume,done in zip(basket.buy_df['volume'], basket.buy_df['done']):
		
		if done < volume:
			A.done = 0
		
	print('\n A.done:',A.done)
	
	#2024-05-07 ÿ�ν����ʼ�������������������ж��Ƿ��Ѿ�ȫ������
	basket.buy_df['done'] = 0
	
	#��ѯ�����Ե�ί��
	order_list = get_trade_detail_data(basket.account, 'stock', 'order',basket.strategy_name)
	
	for order in order_list:
		
		order_code = order.m_strInstrumentID + '.' + order.m_strExchangeID
		
		print('oder:',order.m_strOptName,': ',order_code)
		print('order.m_nVolumeTotal:',order.m_nVolumeTotal)
		
		#����������Ҫ�ֱ������밴�ս�������������
		if order.m_strOptName == '�޼�����': #and order_code in basket.buy_df['code']:
			
			#���δ������ʱ�䲻����������������
			
			if (t0 - basket.buy_df.loc[basket.buy_df['code'] == order_code, 'ordered'] < WITHDRAW_SECS).any():
				continue
			
			#����гɽ��������ѳɽ�����
			if order.m_nOrderStatus in [55,56]:				#55�����ֳɽ�; 56��ȫ���ɽ�
				basket.buy_df.loc[basket.buy_df['code'] == order_code, 'done'] += order.m_nVolumeTraded
			
			#��������ֻ�г���ʱ����Ҫ����ʣ��ί������
			if order.m_nOrderStatus in [48,49,50,51,52,55,86,255]:
				print(f"��ʱ���� ֹͣ�ȴ� {order_code}")
				print('in cancel ί��ʣ����:',order.m_nVolumeTotal,'�ɽ���',order.m_dTradeAmount)
				
				cancel(order.m_strOrderSysID,basket.account,'stock',C)
				#���ó�����־
				A.order_canceled = 1
				#�����������µ���־�͸���ʣ��Ӧ��������
				#�����µ���־
				basket.buy_df.loc[basket.buy_df['code'] == order_code, 'ordered'] = 0
				#ί���������ȥ�ɽ�����Ϊ��һ������ί�еĽ��
				basket.buy_df.loc[basket.buy_df['code'] == order_code, 'value'] -= order.m_dTradeAmount
				
				
		if order.m_strOptName == '�޼�����': #and order_code in basket.sell_df['code']:
			
			#���δ������ʱ�䲻����������������
			if (t0-basket.sell_df.loc[basket.sell_df['code'] == order_code, 'ordered'] < WITHDRAW_SECS).any():
				continue
			#��������ֻ�г���ʱ����Ҫ����ʣ��ί������
			if order.m_nOrderStatus in [48,49,50,51,52,55,86,255]:
				print(f"��ʱ���� ֹͣ�ȴ� {order_code}")
				print('in cancel ί��ʣ����:',order.m_nVolumeTotal)
				cancel(order.m_strOrderSysID,basket.account,'stock',C)
				#���ó�����־
				A.order_canceled = 1
				#�����������µ���־,����ʣ����������
				basket.sell_df.loc[basket.sell_df['code'] == order_code, 'ordered'] = 0
				basket.sell_df.loc[basket.sell_df['code'] == order_code, 'volume'] = order.m_nVolumeTotal
	
	#��鳷����־������г����������µ������������ó�����־����һ�������µ�
	if A.order_canceled == 1:
		print("�г������¸�����ִ��������������")
		A.order_canceled = 0
		return
	
	#�����µ�����������	
	for code,volume,ordered in zip(basket.sell_df['code'], basket.sell_df['volume'], basket.sell_df['ordered']):
		
		#�����¼��������,volume���汾��Ӧ���µ��������������ֳɽ�������Ӧ����ί�е�����
		if(ordered == 0 and volume != 0):
			print('\n����ί��: ', code, '������', volume)
			passorder(	24,					#����
						1101,				#��/�ַ�ʽ�µ�
						basket.account,		#�˺� 
						code,				#��Ʊ���� 
						5,					#���¼�
						0,					#�۸�
						volume,				#����
						basket.strategy_name,	#��������
						2,					#�����µ�
						'',					#�û�orderid
						C)
			#����ί��ʱ���
			basket.sell_df.loc[basket.sell_df['code'] == code, 'ordered'] = t0
	
	#�����µ������ս��	
	for code,value,ordered in zip(basket.buy_df['code'], basket.buy_df['value'],basket.buy_df['ordered']):
		
		#�����¼�������,valueΪ������Ҫ����Ľ��������ֳɽ�������Ӧ����ί�еĽ��
		if(ordered ==0 and value != 0 and basket.cash > value):
			print('\n����ί��: ', code, '��', value)
			passorder(	23,					#����
						1102,				#��ʽ�µ�
						basket.account,		#�˺� 
						code,				#��Ʊ���� 
						5,					#���¼�
						0,					#�۸�
						value,				#����
						basket.strategy_name,	#��������
						2,					#�����µ�
						'',					#�û�orderid
						C)
			#����ί��ʱ���
			basket.buy_df.loc[basket.buy_df['code'] == code, 'ordered'] = t0
			#���¿����ʽ�
			basket.cash -= value
		#�ж��Ƿ������һֻ����ı�ģ�����ǣ�����ʣ������ʽ�����
		elif(ordered ==0 and value != 0 and basket.cash < value):
			print('�����ʽ��㣬���ã�', basket.cash,'Ӧ���룺',code,'��',value)
			#df = basket.buy_df[basket.buy_df['code'] != code]
			#print('last df:',df)
			#����������������Ķ����µ�������ʣ������ʽ����뵱ǰ���
			#2024-04-09: �޸��߼������
			'''
			if df['ordered'].ne(0).all():
				print('\n���һֻ����: ', code, '��', basket.cash)
				passorder(	23,					#����
						1102,				#��ʽ�µ�
						basket.account,		#�˺� 
						code,				#��Ʊ���� 
						5,					#���¼�
						0,					#�۸�
						basket.cash,				#����
						basket.strategy_name,	#��������
						2,					#�����µ�
						'',					#�û�orderid
						C)
				basket.buy_df.loc[basket.buy_df['code'] == code, 'ordered'] = t0
				#���¿����ʽ�
				basket.cash -= value
			'''
