using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Data;
using System.Data.OleDb;
using System.Drawing;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace Stock_from_xls
{
    public partial class Form1 : Form
    {
        string operation = "", tickers = "";
        string URL = "http://download.finance.yahoo.com/d/quotes.csv?s=", browserPath;

        public Form1()
        {
            InitializeComponent();
        }

        private void button2_Click(object sender, EventArgs e)
        {
            string PathConnString = "Provider = Microsoft.Jet.OLEDB.4.0; Data Source =" +
                   textBox_filename.Text +
                   ";Extended Properties=\"Excel 8.0;HDR=Yes\";";
            OleDbConnection conn = new OleDbConnection(PathConnString);
            OleDbDataAdapter myadapter = new OleDbDataAdapter("Select * from [Sheet1$]", conn); // command antstatt string
            DataTable dTable = new DataTable();
            myadapter.Fill(dTable);
            tickers = "";
            foreach (DataRow row in dTable.Rows) // Loop over the rows.
            {
                tickers = tickers + Convert.ToString(row[0]) + ",";
            }
            if (tickers == "")
                MessageBox.Show("ist leer");
            MessageBox.Show(tickers);
     
            dataGridView1.Rows.Add(dTable);

        }

        private void Import_file_button_Click(object sender, EventArgs e)
        {
            OpenFileDialog openFileDialog1 = new OpenFileDialog();
            openFileDialog1.Filter = "XLS Files | *.XLS";
            openFileDialog1.Title = "Please select the .xls for depot Project Application file.";

            if (openFileDialog1.ShowDialog() == System.Windows.Forms.DialogResult.OK)
            {
                this.textBox_filename.Text = openFileDialog1.FileName;

            }

        }

        private void button1_Click(object sender, EventArgs e)
        {
            if (textBox_filename.Text == "")
            {
                MessageBox.Show("ist leer");

            }
            else
            {

                string PathConnString = "Provider = Microsoft.Jet.OLEDB.4.0; Data Source =" +
                        textBox_filename.Text +
                        ";Extended Properties=\"Excel 8.0;HDR=Yes\";";
                OleDbConnection conn = new OleDbConnection(PathConnString);
                OleDbDataAdapter myadapter = new OleDbDataAdapter("Select * from [Sheet1$]", conn); // command antstatt string
                DataTable dTable = new DataTable();
                myadapter.Fill(dTable);
                tickers = "";
                foreach (DataRow row in dTable.Rows) // Loop over the rows.
                {
                    tickers = tickers + Convert.ToString(row[0]) + ",";
                }
                if (tickers == "")
                    MessageBox.Show("ist leer");
                browserPath = URL + tickers + "&f=sl1hg";  //zusammen bauen des STrings  getestet &f=bdc1
                                                               //                browserPath = URL + tickers + "&f=sl1d1t1p2c1ohgvm3m4&e=.csv";  //zusammen bauen des STrings  getestet &f=bdc1
                System.Diagnostics.Process.Start(browserPath);
            }

            }


        // nächste schritte auswerten
        // letzten teil des string dynamsch gestallten
/*
        Financial Data you can Download

Pricing Dividends 
a: Ask y: Dividend Yield 
b: Bid d: Dividend per Share 
b2: Ask (Realtime) r1: Dividend Pay Date 
b3: Bid (Realtime) q: Ex-Dividend Date 
p: Previous Close  
o: Open  
Date 
c1: Change d1: Last Trade Date 
c: Change & Percent Change d2: Trade Date 
c6: Change (Realtime) t1: Last Trade Time 
k2: Change Percent (Realtime)  
p2: Change in Percent  
Averages 
c8: After Hours Change (Realtime) m5: Change From 200 Day Moving Average 
c3: Commission m6: Percent Change From 200 Day Moving Average 
g: Day’s Low m7: Change From 50 Day Moving Average 
h: Day’s High m8: Percent Change From 50 Day Moving Average 
k1: Last Trade (Realtime) With Time m3: 50 Day Moving Average 
l: Last Trade (With Time) m4: 200 Day Moving Average 
l1: Last Trade (Price Only)  
t8: 1 yr Target Price  
Misc 
w1: Day’s Value Change g1: Holdings Gain Percent 
w4: Day’s Value Change (Realtime) g3: Annualized Gain 
p1: Price Paid g4: Holdings Gain 
m: Day’s Range g5: Holdings Gain Percent (Realtime) 
m2: Day’s Range (Realtime) g6: Holdings Gain (Realtime) 
52 Week Pricing Symbol Info 
k: 52 Week High i: More Info 
j: 52 week Low j1: Market Capitalization 
j5: Change From 52 Week Low j3: Market Cap (Realtime) 
k4: Change From 52 week High f6: Float Shares 
j6: Percent Change From 52 week Low n: Name 
k5: Percent Change From 52 week High n4: Notes 
w: 52 week Range s: Symbol 
 s1: Shares Owned 
 x: Stock Exchange 
 j2: Shares Outstanding 
Volume 
v: Volume  
a5: Ask Size  
b6: Bid Size Misc 
k3: Last Trade Size t7: Ticker Trend 
a2: Average Daily Volume t6: Trade Links 
 i5: Order Book (Realtime) 
Ratios l2: High Limit 
e: Earnings per Share l3: Low Limit 
e7: EPS Estimate Current Year v1: Holdings Value 
e8: EPS Estimate Next Year v7: Holdings Value (Realtime) 
e9: EPS Estimate Next Quarter s6 Revenue 
b4: Book Value  
j4: EBITDA  
p5: Price / Sales  
p6: Price / Book  
r: P/E Ratio  
r2: P/E Ratio (Realtime)  
r5: PEG Ratio  
r6: Price / EPS Estimate Current Year  
r7: Price / EPS Estimate Next Year  
s7: Short Ratio 
*/

    }
}
