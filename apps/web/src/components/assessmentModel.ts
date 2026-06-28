import type { ComprehensiveAssessmentPayload, LessonState } from "../api/client";

export interface AssessmentQuizItem {
  id: string;
  dimension: string;
  prompt: string;
  options: string[];
  answer: number;
  weight: number;
}

export interface CodeAssessmentAttemptInput {
  prompt: string;
  code: string;
  expectedOutput: string;
  actualOutput: string;
  passed: boolean;
  attempts: number;
}

export interface AssessmentContextInput {
  courseName?: string;
  exerciseContent?: string;
  topic: string;
}

export interface CodeAssessmentChallenge {
  prompt: string;
  starterCode: string;
  expectedOutput: string;
}

interface ParsedExerciseAssessment {
  codeChallenge?: CodeAssessmentChallenge;
  quizItems: AssessmentQuizItem[];
}

export const assessmentQuizItems: AssessmentQuizItem[] = [
  {
    id: "concept",
    dimension: "概念理解",
    prompt: "下面哪一项最能说明你真正理解了本节知识点？",
    options: ["能判断它解决的问题、适用条件和典型误区", "能说出课堂标题", "能记住材料页码"],
    answer: 0,
    weight: 0.35
  },
  {
    id: "transfer",
    dimension: "迁移应用",
    prompt: "面对一个相近问题时，哪种表现代表已经具备迁移能力？",
    options: ["照抄示例代码", "能选择相似方法并说明为什么适用", "只看运行结果"],
    answer: 1,
    weight: 0.3
  },
  {
    id: "debugging",
    dimension: "调试反思",
    prompt: "代码运行结果不符合预期时，优先应该做什么？",
    options: ["随意改几行再试", "定位输入、过程和输出的差异", "直接跳过本节"],
    answer: 1,
    weight: 0.35
  }
];

const fallbackQuizTemplates: Partial<Record<AssessmentTemplateKey, AssessmentQuizItem[]>> = {
  python_version: [
    {
      id: "concept",
      dimension: "概念理解",
      prompt: "围绕“{topic}”，关于 Python 2 与 Python 3 的差异，哪一项判断更准确？",
      options: [
        "Python 3 改进了文本编码处理，并调整了 print 等常见语法形式",
        "Python 2 与 Python 3 的语法和标准库完全兼容",
        "Python 版本只影响编辑器主题，不会影响程序运行"
      ],
      answer: 0,
      weight: 0.35
    },
    {
      id: "transfer",
      dimension: "迁移应用",
      prompt: "学习“{topic}”后，在选择项目运行环境时，为什么要确认 Python 版本？",
      options: [
        "因为库的兼容范围、语法特性和解释器行为都可能依赖具体版本",
        "因为版本号越长，程序运行速度一定越快",
        "因为 Python 版本只用于给文件命名"
      ],
      answer: 0,
      weight: 0.3
    },
    {
      id: "debugging",
      dimension: "调试反思",
      prompt: "围绕“{topic}”，教材中的旧示例出现 `SyntaxError: Missing parentheses in call to 'print'`，最可能的原因是什么？",
      options: [
        "在 Python 3 环境中运行了 Python 2 风格的 print 语句",
        "变量名一定和关键字冲突",
        "操作系统不支持 Python 解释器"
      ],
      answer: 0,
      weight: 0.35
    }
  ],
  python_application: [
    {
      id: "concept",
      dimension: "概念理解",
      prompt: "围绕“{topic}”，Python 能覆盖自动化、数据分析、Web 与人工智能等领域，关键原因是什么？",
      options: [
        "语法表达简洁，并且拥有成熟的第三方库和生态工具",
        "Python 只能编写命令行输出程序",
        "Python 不需要解释器也能直接运行"
      ],
      answer: 0,
      weight: 0.35
    },
    {
      id: "transfer",
      dimension: "迁移应用",
      prompt: "如果要快速处理一批 Excel 表格并生成统计图，哪种判断最符合“{topic}”的应用思路？",
      options: [
        "优先考虑 pandas、openpyxl、matplotlib 等库组合完成数据处理与可视化",
        "只能手工复制粘贴数据，不能用程序自动化",
        "必须先重写操作系统才能处理表格"
      ],
      answer: 0,
      weight: 0.3
    },
    {
      id: "debugging",
      dimension: "调试反思",
      prompt: "围绕“{topic}”，在某个应用领域选择 Python 后，如果库导入失败，首先应该检查什么？",
      options: [
        "当前解释器环境、依赖安装状态和包名是否正确",
        "显示器分辨率是否足够高",
        "变量注释是否写得足够长"
      ],
      answer: 0,
      weight: 0.35
    }
  ],
  python_feature: [
    {
      id: "concept",
      dimension: "概念理解",
      prompt: "围绕“{topic}”，下列哪项更符合 Python 程序设计的语言特点？",
      options: [
        "语法简洁、解释执行、库生态丰富，适合快速开发和验证想法",
        "必须先手动管理所有内存地址才能运行",
        "只能用于网页排版，不能编写算法程序"
      ],
      answer: 0,
      weight: 0.35
    },
    {
      id: "transfer",
      dimension: "迁移应用",
      prompt: "把“{topic}”迁移到一个小型数据处理脚本时，最合理的做法是什么？",
      options: [
        "利用清晰变量名、函数拆分和标准库/第三方库提高可读性与开发效率",
        "把所有逻辑写在一行里，越短越好",
        "只复制别人的输出结果，不关心代码结构"
      ],
      answer: 0,
      weight: 0.3
    },
    {
      id: "debugging",
      dimension: "调试反思",
      prompt: "围绕“{topic}”，Python 脚本运行出现模块找不到或类型不匹配时，最应该怎么排查？",
      options: [
        "确认运行解释器、依赖环境、输入类型和异常栈定位到的代码行",
        "直接删除所有 import 语句",
        "只修改文件名，不检查报错信息"
      ],
      answer: 0,
      weight: 0.35
    }
  ],
  c_io: [
    {
      id: "concept",
      dimension: "概念理解",
      prompt: "围绕“{topic}”，scanf 读取普通变量时常使用 `&` 的原因是什么？",
      options: [
        "scanf 需要变量地址，才能把输入值写入对应内存位置",
        "`&` 表示把变量转换成字符串",
        "`&` 的作用是让程序自动换行"
      ],
      answer: 0,
      weight: 0.35
    },
    {
      id: "transfer",
      dimension: "迁移应用",
      prompt: "要读取一个整数 n 并输出 n+1，哪种代码思路符合“{topic}”？",
      options: [
        "使用 `scanf(\"%d\", &n)` 读取，再用 `printf` 输出计算结果",
        "只写 `printf`，不需要任何变量保存输入",
        "使用 `%f` 读取所有整数，类型无关紧要"
      ],
      answer: 0,
      weight: 0.3
    },
    {
      id: "debugging",
      dimension: "调试反思",
      prompt: "围绕“{topic}”，C 程序输入后变量值异常，优先应该检查哪一项？",
      options: [
        "格式控制符是否匹配变量类型，以及是否传入了正确地址",
        "源文件名是否足够长",
        "注释是否写在每一行前面"
      ],
      answer: 0,
      weight: 0.35
    }
  ],
  python_variable: [
    {
      id: "concept",
      dimension: "概念理解",
      prompt: "围绕“{topic}”，在 Python 中，下列哪个变量名是不合法的？",
      options: [
        "_my_var",
        "2nd_value",
        "userName",
        "PI"
      ],
      answer: 1,
      weight: 0.35
    },
    {
      id: "transfer",
      dimension: "迁移应用",
      prompt: "围绕“{topic}”，如果要把用户输入的两个整数相加，哪种写法最合理？",
      options: [
        "使用 `num1 = int(input())` 和 `num2 = int(input())` 先完成类型转换，再进行加法",
        "直接把两个 `input()` 的返回值相加，因为 input() 默认返回整数",
        "只使用 `print(input())`，不需要变量保存和类型转换"
      ],
      answer: 0,
      weight: 0.3
    },
    {
      id: "debugging",
      dimension: "调试反思",
      prompt: "围绕“{topic}”，代码 `2nd_value = 10` 报错，最准确的原因是什么？",
      options: [
        "Python 变量名不能以数字开头，应该改成符合标识符规则的名称",
        "Python 变量名不能包含下划线",
        "Python 中所有变量赋值前都必须先声明类型"
      ],
      answer: 0,
      weight: 0.35
    }
  ],
  python_pseudocode: [
    {
      id: "concept",
      dimension: "概念理解",
      prompt: "围绕“{topic}”，下列哪一段最符合“用伪代码表示算法”的表达要求？",
      options: [
        "输入 n；如果 n 是偶数则输出“偶数”，否则输出“奇数”",
        "这个算法很重要，需要认真学习",
        "Python 程序只要能运行，就不需要描述步骤"
      ],
      answer: 0,
      weight: 0.35
    },
    {
      id: "transfer",
      dimension: "迁移应用",
      prompt: "围绕“{topic}”，要用伪代码描述“求 1 到 n 的累加和”，哪种步骤最合理？",
      options: [
        "输入 n；sum 置 0；从 1 循环到 n，把当前数累加到 sum；输出 sum",
        "只写“计算累加和”，不说明输入、循环和输出",
        "先输出结果，再决定 n 的取值"
      ],
      answer: 0,
      weight: 0.3
    },
    {
      id: "debugging",
      dimension: "调试反思",
      prompt: "围绕“{topic}”，如果伪代码漏写循环终止条件，最可能导致什么问题？",
      options: [
        "算法步骤不完整，无法判断循环何时结束，后续转成程序时容易出现死循环或结果错误",
        "变量名一定不合法",
        "Python 解释器版本一定不兼容"
      ],
      answer: 0,
      weight: 0.35
    }
  ],
  python_branch: [
    {
      id: "concept",
      dimension: "概念理解",
      prompt: "围绕“{topic}”，Python 中 if 条件分支的执行规则哪一项正确？",
      options: [
        "条件表达式为 True 时执行 if 代码块，否则可进入 elif 或 else 分支",
        "if 和 else 两个代码块每次都会同时执行",
        "条件分支只能判断数字，不能判断比较表达式"
      ],
      answer: 0,
      weight: 0.35
    },
    {
      id: "transfer",
      dimension: "迁移应用",
      prompt: "围绕“{topic}”，要根据 score 是否大于等于 60 输出“及格/不及格”，最合理的结构是什么？",
      options: [
        "使用 `if score >= 60:` 处理及格情况，并用 `else:` 处理不及格情况",
        "只写两个连续的 print，不需要条件判断",
        "使用 input() 就会自动判断是否及格"
      ],
      answer: 0,
      weight: 0.3
    },
    {
      id: "debugging",
      dimension: "调试反思",
      prompt: "围绕“{topic}”，if 语句缩进错误最可能造成什么结果？",
      options: [
        "分支代码块归属错误，可能触发 IndentationError 或导致逻辑路径不符合预期",
        "变量名会自动变成全局变量",
        "else 会自动补全缺失的条件"
      ],
      answer: 0,
      weight: 0.35
    }
  ],
  python_loop: [
    {
      id: "concept",
      dimension: "概念理解",
      prompt: "围绕“{topic}”，`for i in range(1, 5)` 会依次产生哪些 i 值？",
      options: [
        "1、2、3、4",
        "1、2、3、4、5",
        "0、1、2、3、4、5"
      ],
      answer: 0,
      weight: 0.35
    },
    {
      id: "transfer",
      dimension: "迁移应用",
      prompt: "围绕“{topic}”，要计算 1 到 n 的累加和，循环体中最关键的语句是什么？",
      options: [
        "`total = total + i`，把当前循环变量累加到 total",
        "`total = i`，每次覆盖之前的结果",
        "`print(i)`，打印循环变量就等于完成累加"
      ],
      answer: 0,
      weight: 0.3
    },
    {
      id: "debugging",
      dimension: "调试反思",
      prompt: "围绕“{topic}”，循环结果少算最后一个数时，优先应该检查什么？",
      options: [
        "range 的结束边界是否是左闭右开，以及循环变量是否覆盖了目标范围",
        "print 的字体大小是否合适",
        "Python 文件名是否包含中文"
      ],
      answer: 0,
      weight: 0.35
    }
  ],
  python_function: [
    {
      id: "concept",
      dimension: "概念理解",
      prompt: "围绕“{topic}”，Python 函数定义中 def、参数和 return 的作用哪项正确？",
      options: [
        "def 定义可复用逻辑，参数接收外部数据，return 把结果返回给调用处",
        "def 只能定义变量，return 只能打印文本",
        "函数参数只能是字符串，不能是数字"
      ],
      answer: 0,
      weight: 0.35
    },
    {
      id: "transfer",
      dimension: "迁移应用",
      prompt: "围绕“{topic}”，要封装一个求两个数最大值的函数，哪种设计更合理？",
      options: [
        "`def max_value(a, b):` 接收两个参数，并用 return 返回较大的值",
        "在函数内部固定写死 a=1、b=2，不接收参数",
        "只在函数里 print，不考虑调用处是否需要继续使用结果"
      ],
      answer: 0,
      weight: 0.3
    },
    {
      id: "debugging",
      dimension: "调试反思",
      prompt: "围绕“{topic}”，函数调用结果是 None，最可能需要检查什么？",
      options: [
        "函数体是否缺少 return，或者 return 是否只写在某个分支里",
        "文件扩展名是否必须改成 .txt",
        "参数名是否必须叫 number"
      ],
      answer: 0,
      weight: 0.35
    }
  ],
  python_sequence: [
    {
      id: "concept",
      dimension: "概念理解",
      prompt: "围绕“{topic}”，Python 列表索引和遍历的说法哪项正确？",
      options: [
        "列表下标从 0 开始，可以用 for 循环依次访问元素",
        "列表下标从 1 开始，不能通过循环访问",
        "列表只能保存一个元素"
      ],
      answer: 0,
      weight: 0.35
    },
    {
      id: "transfer",
      dimension: "迁移应用",
      prompt: "围绕“{topic}”，要统计列表 nums 中所有元素的和，哪种思路最合理？",
      options: [
        "初始化 total，再遍历 nums，把每个元素累加到 total",
        "只访问 nums[0]，它一定代表所有元素之和",
        "把列表转成字符串后直接相加"
      ],
      answer: 0,
      weight: 0.3
    },
    {
      id: "debugging",
      dimension: "调试反思",
      prompt: "围绕“{topic}”，访问列表时出现 IndexError，优先应该检查什么？",
      options: [
        "索引是否超出 `0` 到 `len(list)-1` 的有效范围",
        "变量名是否必须叫 list",
        "是否没有导入 math 模块"
      ],
      answer: 0,
      weight: 0.35
    }
  ],
  python_file: [
    {
      id: "concept",
      dimension: "概念理解",
      prompt: "围绕“{topic}”，Python 使用 open 读取文件时，哪项说法正确？",
      options: [
        "`open(path, 'r', encoding='utf-8')` 可打开文本文件读取内容，用完应关闭或使用 with 管理",
        "`open()` 只能创建文件，不能读取文件",
        "读取文件不需要路径，也不需要处理编码"
      ],
      answer: 0,
      weight: 0.35
    },
    {
      id: "transfer",
      dimension: "迁移应用",
      prompt: "围绕“{topic}”，要逐行读取文本文件并统计行数，哪种思路最合理？",
      options: [
        "使用 `with open(...) as f:` 打开文件，再遍历文件对象累加行数",
        "只调用一次 print，不需要读取文件内容",
        "把文件名赋值给变量就能得到所有行数"
      ],
      answer: 0,
      weight: 0.3
    },
    {
      id: "debugging",
      dimension: "调试反思",
      prompt: "围绕“{topic}”，读取文件时出现乱码，优先应该检查什么？",
      options: [
        "文件实际编码和 open 中指定的 encoding 是否一致",
        "循环变量是否叫 i",
        "是否写了太多注释"
      ],
      answer: 0,
      weight: 0.35
    }
  ],
  c_array: [
    {
      id: "concept",
      dimension: "概念理解",
      prompt: "围绕“{topic}”，C 语言一维数组 `int a[5]` 的下标范围哪项正确？",
      options: [
        "有效下标是 0 到 4",
        "有效下标是 1 到 5",
        "有效下标是 0 到 5"
      ],
      answer: 0,
      weight: 0.35
    },
    {
      id: "transfer",
      dimension: "迁移应用",
      prompt: "围绕“{topic}”，要累加数组 a 中 5 个整数，哪种循环边界更合理？",
      options: [
        "`for (i = 0; i < 5; i++)` 依次访问 a[i]",
        "`for (i = 1; i <= 5; i++)` 依次访问 a[i]，不会越界",
        "不需要循环，数组会自动求和"
      ],
      answer: 0,
      weight: 0.3
    },
    {
      id: "debugging",
      dimension: "调试反思",
      prompt: "围绕“{topic}”，数组访问越界最可能带来什么问题？",
      options: [
        "读写未定义内存位置，导致结果异常或程序崩溃",
        "数组长度会自动扩大",
        "编译器一定会自动修复下标"
      ],
      answer: 0,
      weight: 0.35
    }
  ],
  c_pointer: [
    {
      id: "concept",
      dimension: "概念理解",
      prompt: "围绕“{topic}”，C 语言中 `&x` 和 `*p` 的含义哪项正确？",
      options: [
        "`&x` 取得变量 x 的地址，`*p` 访问指针 p 指向地址中的值",
        "`&x` 表示乘法，`*p` 表示字符串",
        "指针变量只能保存普通整数，不能保存地址"
      ],
      answer: 0,
      weight: 0.35
    },
    {
      id: "transfer",
      dimension: "迁移应用",
      prompt: "围绕“{topic}”，若 `int x = 3; int *p = &x;`，执行 `*p = 5;` 后 x 的值是什么？",
      options: [
        "5",
        "3",
        "无法确定，因为 p 没有指向 x"
      ],
      answer: 0,
      weight: 0.3
    },
    {
      id: "debugging",
      dimension: "调试反思",
      prompt: "围绕“{topic}”，使用指针前最应该确认什么？",
      options: [
        "指针是否已经指向有效地址，避免野指针或空指针解引用",
        "指针变量名是否必须叫 p",
        "是否所有指针都必须指向数组"
      ],
      answer: 0,
      weight: 0.35
    }
  ],
  c_function: [
    {
      id: "concept",
      dimension: "概念理解",
      prompt: "围绕“{topic}”，C 语言函数定义中返回类型、参数和 return 的作用哪项正确？",
      options: [
        "返回类型说明返回值类型，参数接收调用者传入的数据，return 返回结果并结束函数",
        "所有函数都不能有参数",
        "return 只能在 main 函数中使用"
      ],
      answer: 0,
      weight: 0.35
    },
    {
      id: "transfer",
      dimension: "迁移应用",
      prompt: "围绕“{topic}”，要定义一个求两个 int 最大值的函数，哪种函数头更合理？",
      options: [
        "`int max(int a, int b)`",
        "`void max()` 且不接收任何参数",
        "`char max(int a, int b)` 且返回字符串"
      ],
      answer: 0,
      weight: 0.3
    },
    {
      id: "debugging",
      dimension: "调试反思",
      prompt: "围绕“{topic}”，函数返回值异常时优先检查什么？",
      options: [
        "参数传入是否正确、分支是否都有 return、返回类型是否匹配",
        "源文件是否必须放在桌面",
        "注释是否超过三行"
      ],
      answer: 0,
      weight: 0.35
    }
  ],
  generic_programming: [
    {
      id: "concept",
      dimension: "概念理解",
      prompt: "围绕“{topic}”，下列哪项最能体现该知识点的核心作用？",
      options: [
        "能说明它解决的问题、适用条件、输入输出关系和常见错误",
        "只知道它出现在本节课中",
        "只知道它对应教材中的某一页"
      ],
      answer: 0,
      weight: 0.35
    },
    {
      id: "transfer",
      dimension: "迁移应用",
      prompt: "把“{topic}”用于一个新的编程场景时，最合理的判断是什么？",
      options: [
        "根据问题特征选择相关语法或方法，并能解释为什么适用",
        "完全照抄示例，不分析新问题差异",
        "只运行一次，不检查边界情况"
      ],
      answer: 0,
      weight: 0.3
    },
    {
      id: "debugging",
      dimension: "调试反思",
      prompt: "“{topic}”相关练习结果不符合预期时，优先应该怎么做？",
      options: [
        "沿着输入、状态变化、关键语句和输出逐步定位问题",
        "随机改动多处代码后立即提交",
        "跳过该知识点，继续下一个任务"
      ],
      answer: 0,
      weight: 0.35
    }
  ]
};

type AssessmentTemplateKey =
  | "python_version"
  | "python_application"
  | "python_feature"
  | "python_variable"
  | "python_pseudocode"
  | "python_branch"
  | "python_loop"
  | "python_function"
  | "python_sequence"
  | "python_file"
  | "c_io"
  | "c_array"
  | "c_pointer"
  | "c_function"
  | "generic_programming";

export function buildAssessmentQuizItems(input: AssessmentContextInput): AssessmentQuizItem[] {
  const parsed = parseExerciseAssessment(input.exerciseContent);
  const topic = cleanTopic(input.topic);
  const courseName = input.courseName?.trim() || "当前课程";
  if (parsed.quizItems.length >= 3 && isHighQualityQuizSet(parsed.quizItems, courseName, topic)) {
    return parsed.quizItems.slice(0, 3);
  }
  return professionalFallbackQuiz(courseName, topic);
}

export function buildCodeAssessmentChallenge(input: AssessmentContextInput): CodeAssessmentChallenge {
  const parsed = parseExerciseAssessment(input.exerciseContent);
  const topic = cleanTopic(input.topic);
  const courseName = input.courseName?.trim() || "";
  if (parsed.codeChallenge && isHighQualityCodeChallenge(parsed.codeChallenge, courseName, topic)) {
    return parsed.codeChallenge;
  }
  return professionalFallbackCodeChallenge(courseName, topic);
}

export function parseExerciseAssessment(content?: string): ParsedExerciseAssessment {
  if (!content?.trim()) {
    return { quizItems: [] };
  }
  const lines = content.split(/\r?\n/);
  const quizItems: AssessmentQuizItem[] = [];
  let current: Partial<AssessmentQuizItem> & { answerLabel?: string } | undefined;
  let codePrompt = "";
  let starterCode = "";
  let expectedOutput = "";
  let inCodeBlock = false;
  const codeLines: string[] = [];

  function flushCurrent() {
    const options = (current?.options || []).map(cleanAssessmentText).filter(Boolean);
    if (!current?.prompt || options.length < 3) {
      return;
    }
    const answer = answerIndex(current.answerLabel, options);
    quizItems.push({
      id: current.id || `agent_${quizItems.length + 1}`,
      dimension: current.dimension || dimensionForIndex(quizItems.length),
      prompt: current.prompt,
      options: options.slice(0, 4),
      answer,
      weight: current.weight || weightForIndex(quizItems.length)
    });
  }

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) {
      continue;
    }
    if (/^```/.test(line)) {
      inCodeBlock = !inCodeBlock;
      continue;
    }
    if (inCodeBlock) {
      codeLines.push(rawLine);
      continue;
    }
    const questionMatch = line.match(/^(?:#{1,6}\s*)?(?:题目|问题|Q|选择题)?\s*(\d+)[\.、:)：]\s*(.+)$/i);
    const bulletQuestionMatch = line.match(/^[-*]\s*(?:题目|问题|Q|选择题)\s*(\d*)[：:]\s*(.+)$/i);
    if (questionMatch || bulletQuestionMatch) {
      const [, rawNumber = "", rawPrompt = ""] = questionMatch || bulletQuestionMatch || [];
      flushCurrent();
      current = {
        id: questionId(rawNumber, quizItems.length),
        options: [],
        prompt: cleanAssessmentText(rawPrompt)
      };
      continue;
    }
    const optionMatch = line.match(/^(?:[-*]\s*)?([A-Da-d])[\.、:)：]\s*(.+)$/);
    if (optionMatch && current) {
      current.options = [...(current.options || []), cleanAssessmentText(optionMatch[2])];
      continue;
    }
    const answerMatch = line.match(/^(?:参考答案|正确答案|答案|answer)\s*[：:]\s*([A-Da-d]|.+)$/i);
    if (answerMatch) {
      if (current) {
        current.answerLabel = answerMatch[1].trim();
      } else if (!expectedOutput) {
        expectedOutput = stripQuotes(answerMatch[1].trim());
      }
      continue;
    }
    const dimensionMatch = line.match(/^(?:维度|能力维度|考察维度)\s*[：:]\s*(.+)$/);
    if (dimensionMatch && current) {
      current.dimension = cleanAssessmentText(dimensionMatch[1]);
      continue;
    }
    const weightMatch = line.match(/^(?:权重|分值)\s*[：:]\s*(\d+(?:\.\d+)?)%?/);
    if (weightMatch && current) {
      const value = Number(weightMatch[1]);
      current.weight = value > 1 ? value / 100 : value;
      continue;
    }
    const codePromptMatch = line.match(/^(?:编程题|代码题|程序题|上机题)\s*[：:]\s*(.+)$/);
    if (codePromptMatch) {
      codePrompt = cleanAssessmentText(codePromptMatch[1]);
      flushCurrent();
      current = undefined;
      continue;
    }
    const expectedMatch = line.match(/^(?:期望输出|预期输出|expected output)\s*[：:]\s*(.+)$/i);
    if (expectedMatch) {
      expectedOutput = stripQuotes(expectedMatch[1].trim());
      continue;
    }
    const starterMatch = line.match(/^(?:起始代码|初始代码|starter code)\s*[：:]\s*(.+)$/i);
    if (starterMatch) {
      starterCode = cleanAssessmentText(starterMatch[1]);
    }
  }
  flushCurrent();

  const codeChallenge = codePrompt
    ? {
        prompt: codePrompt,
        starterCode: starterCode || codeLines.join("\n") || "# 请在这里完成代码\n",
        expectedOutput: expectedOutput || inferExpectedOutput(codePrompt)
      }
    : undefined;

  return { codeChallenge, quizItems: normalizeWeights(quizItems) };
}

export function codeAttemptMatchesChallenge(expectedOutput: string, actualOutput: string): boolean {
  const expected = normalizeOutput(expectedOutput);
  const actual = normalizeOutput(actualOutput);
  return Boolean(expected) && expected === actual;
}

export function previewQuizScore(
  answers: Record<string, number>,
  items: AssessmentQuizItem[] = assessmentQuizItems
): number {
  const answeredItems = items.filter((item) => answers[item.id] !== undefined);
  const totalWeight = answeredItems.reduce((sum, item) => sum + item.weight, 0);
  if (!totalWeight) {
    return 0;
  }
  const earned = answeredItems.reduce((sum, item) => sum + (answers[item.id] === item.answer ? item.weight : 0), 0);
  return clampScore(earned / totalWeight);
}

export function buildComprehensiveAssessmentPayload(input: {
  answers: Record<string, number>;
  codeAttempt: CodeAssessmentAttemptInput;
  quizItems?: AssessmentQuizItem[];
  courseId?: number;
  lessonState?: LessonState;
  nodeId?: string;
  studentId: string;
  topic: string;
}): ComprehensiveAssessmentPayload {
  const quizItems = input.quizItems?.length ? input.quizItems : assessmentQuizItems;
  return {
    student_id: input.studentId,
    topic: input.topic,
    course_id: input.courseId,
    knowledge_node_id: input.nodeId || "",
    classroom_completed: Boolean(input.lessonState?.classroom_completed),
    notes_completed: Boolean(input.lessonState?.notes_completed),
    mind_map_completed: Boolean(input.lessonState?.mind_map_completed),
    code_lab_completed: Boolean(input.lessonState?.code_lab_completed || input.codeAttempt.passed),
    quiz_answers: quizItems.map((item) => ({
      id: item.id,
      dimension: item.dimension,
      correct: input.answers[item.id] === item.answer,
      prompt: item.prompt,
      options: item.options,
      correct_answer_index: item.answer,
      selected_answer_index: input.answers[item.id],
      weight: item.weight
    })),
    code_attempt: {
      prompt: input.codeAttempt.prompt,
      code: input.codeAttempt.code,
      expected_output: input.codeAttempt.expectedOutput,
      actual_output: input.codeAttempt.actualOutput,
      passed: input.codeAttempt.passed,
      attempts: Math.max(1, input.codeAttempt.attempts)
    },
    detail: `${input.topic} 综合评估：选择题 ${Math.round(previewQuizScore(input.answers, quizItems) * 100)}%，代码题${input.codeAttempt.passed ? "通过" : "未通过"}`
  };
}

export { expectedCodeOutputForAssessment } from "./assessmentExpectedOutputModel";

export function masteryStatusLabel(score: number): string {
  if (score < 0.6) {
    return "严重弱项";
  }
  if (score < 0.75) {
    return "掌握基础";
  }
  if (score < 0.9) {
    return "达标良好";
  }
  return "精通";
}

export function clampScore(score: number): number {
  return Math.max(0, Math.min(1, score));
}

function cleanTopic(topic: string): string {
  return topic.trim() || "当前知识点";
}

function courseLanguage(courseName: string, topic: string): "C语言" | "Python" {
  const text = `${courseName} ${topic}`.toLowerCase();
  return text.includes("c语言") || text.includes("c 语言") ? "C语言" : "Python";
}

function professionalFallbackQuiz(courseName: string, topic: string): AssessmentQuizItem[] {
  const templateKey = fallbackTemplateKey(courseName, topic);
  const templates = fallbackQuizTemplates[templateKey] || fallbackQuizTemplates.generic_programming || [];
  return normalizeWeights(templates.map((item) => ({
    ...item,
    prompt: item.prompt.replace(/\{topic\}/g, topic),
    options: item.options.map((option) => option.replace(/\{topic\}/g, topic))
  })));
}

function professionalFallbackCodeChallenge(courseName: string, topic: string): CodeAssessmentChallenge {
  const templateKey = fallbackTemplateKey(courseName, topic);
  if (courseLanguage(courseName, topic) === "C语言") {
    if (templateKey === "c_array") {
      return {
        prompt: `编程题：围绕“${topic}”，补全 C 程序，定义一维数组 a，计算 3 个整数元素的和并输出。只输出一行数字。`,
        starterCode: [
          "#include <stdio.h>",
          "int main() {",
          "  int a[3] = {2, 4, 6};",
          "  int sum = 0;",
          "  // 请使用 for 循环累加数组元素",
          "  // 请输出 sum",
          "  return 0;",
          "}"
        ].join("\n"),
        expectedOutput: "12"
      };
    }
    if (templateKey === "c_pointer") {
      return {
        prompt: `编程题：围绕“${topic}”，补全 C 程序，通过指针 p 修改变量 x 的值，并输出 x。只输出一行数字。`,
        starterCode: [
          "#include <stdio.h>",
          "int main() {",
          "  int x = 3;",
          "  int *p = &x;",
          "  // 请通过 *p 把 x 修改为 5",
          "  // 请输出 x",
          "  return 0;",
          "}"
        ].join("\n"),
        expectedOutput: "5"
      };
    }
    if (templateKey === "c_function") {
      return {
        prompt: `编程题：围绕“${topic}”，补全 C 程序，调用 max 函数返回两个整数中的较大值并输出。只输出一行数字。`,
        starterCode: [
          "#include <stdio.h>",
          "int max(int a, int b) {",
          "  // 请返回较大的整数",
          "}",
          "int main() {",
          "  // 请输出 max(4, 9) 的结果",
          "  return 0;",
          "}"
        ].join("\n"),
        expectedOutput: "9"
      };
    }
    if (templateKey === "c_io") {
      return {
        prompt: `编程题：围绕“${topic}”，补全 C 程序，定义整数变量 value 为 7，并用 printf 输出 value 加 1 的结果。只输出一行数字。`,
        starterCode: [
          "#include <stdio.h>",
          "int main() {",
          "  int value = 7;",
          "  // 请补全 printf，输出 value + 1",
          "  return 0;",
          "}"
        ].join("\n"),
        expectedOutput: "8"
      };
    }
    return {
      prompt: `编程题：围绕“${topic}”，补全 C 程序，输出 C 程序入口函数的名称。只输出一行文本。`,
      starterCode: [
        "#include <stdio.h>",
        "int main() {",
        "  // 请补全 printf，输出入口函数名称",
        "  return 0;",
        "}"
      ].join("\n"),
      expectedOutput: "main"
    };
  }

  if (templateKey === "python_version") {
    return {
      prompt: `编程题：围绕“${topic}”，补全 Python 程序，使用变量 major 表示 Python 主版本号，并输出“Python 3”。只输出这一行文本。`,
      starterCode: [
        "language = 'Python'",
        "major = 3",
        "# 请补全输出语句"
      ].join("\n"),
      expectedOutput: "Python 3"
    };
  }
  if (templateKey === "python_application") {
    return {
      prompt: `编程题：围绕“${topic}”，补全 Python 程序，把应用领域列表中的第 2 项输出出来。只输出这一行文本。`,
      starterCode: [
        "domains = ['自动化', '数据分析', '人工智能']",
        "# 请补全输出语句，输出 domains 中的数据分析"
      ].join("\n"),
      expectedOutput: "数据分析"
    };
  }
  if (templateKey === "python_variable") {
    return {
      prompt: `编程题：变量交换与输入输出。围绕“${topic}”，编写 Python 程序：使用 input() 接收两个整数，分别赋值给变量 num1 和 num2；先输出交换前两个变量的值；再交换两个变量；最后输出交换后的值。测试输入固定为两行：3 和 8。`,
      starterCode: [
        "# 测试输入固定为两行：3 和 8",
        "num1 = int(input())",
        "num2 = int(input())",
        "# 请输出交换前两个变量的值，格式：交换前：num1=3, num2=8",
        "# 请交换 num1 和 num2",
        "# 请输出交换后两个变量的值，格式：交换后：num1=8, num2=3"
      ].join("\n"),
      expectedOutput: "交换前：num1=3, num2=8\n交换后：num1=8, num2=3"
    };
  }
  if (templateKey === "python_pseudocode") {
    return {
      prompt: `编程题：围绕“${topic}”，把“输入一个整数 n，输出 1 到 n 的累加和”这一伪代码过程转成 Python 程序。测试输入固定为 5，只输出累加和结果。`,
      starterCode: [
        "# 测试输入固定为一行：5",
        "n = int(input())",
        "total = 0",
        "# 请使用循环把 1 到 n 累加到 total",
        "# 请输出 total"
      ].join("\n"),
      expectedOutput: "15"
    };
  }
  if (templateKey === "python_branch") {
    return {
      prompt: `编程题：围绕“${topic}”，补全 Python 程序，根据 score 的值输出“及格”或“不及格”。测试 score 固定为 72，只输出判断结果。`,
      starterCode: [
        "score = 72",
        "# 请使用 if/else 判断 score 是否大于等于 60",
        "# 请输出：及格"
      ].join("\n"),
      expectedOutput: "及格"
    };
  }
  if (templateKey === "python_loop") {
    return {
      prompt: `编程题：围绕“${topic}”，补全 Python 程序，使用 for 和 range 计算 1 到 5 的累加和。只输出一行数字。`,
      starterCode: [
        "total = 0",
        "# 请使用 for i in range(1, 6) 完成累加",
        "# 请输出 total"
      ].join("\n"),
      expectedOutput: "15"
    };
  }
  if (templateKey === "python_function") {
    return {
      prompt: `编程题：围绕“${topic}”，补全 Python 函数 max_value(a, b)，用 return 返回较大的数，并输出 max_value(4, 9)。只输出一行数字。`,
      starterCode: [
        "def max_value(a, b):",
        "    # 请返回 a 和 b 中较大的值",
        "",
        "# 请输出 max_value(4, 9)"
      ].join("\n"),
      expectedOutput: "9"
    };
  }
  if (templateKey === "python_sequence") {
    return {
      prompt: `编程题：围绕“${topic}”，补全 Python 程序，遍历列表 nums 并输出所有元素之和。只输出一行数字。`,
      starterCode: [
        "nums = [2, 4, 6]",
        "total = 0",
        "# 请遍历 nums，把每个元素累加到 total",
        "# 请输出 total"
      ].join("\n"),
      expectedOutput: "12"
    };
  }
  if (templateKey === "python_file") {
    return {
      prompt: `编程题：围绕“${topic}”，模拟文件读取结果 lines，补全 Python 程序输出文本行数。只输出一行数字。`,
      starterCode: [
        "lines = ['第一行', '第二行', '第三行']",
        "# 请输出 lines 的长度，模拟 open 读取后的行数统计"
      ].join("\n"),
      expectedOutput: "3"
    };
  }
  return {
    prompt: `编程题：围绕“${topic}”，补全 Python 程序，把 language 与 feature 两个变量组合成“Python 简洁”。只输出这一行文本。`,
    starterCode: [
      "language = 'Python'",
      "feature = '简洁'",
      "# 请补全输出语句"
    ].join("\n"),
    expectedOutput: "Python 简洁"
  };
}

function fallbackTemplateKey(courseName: string, topic: string): AssessmentTemplateKey {
  const text = `${courseName} ${topic}`.toLowerCase();
  if (text.includes("c语言") || text.includes("c 语言")) {
    if (text.includes("数组") || text.includes("下标") || text.includes("一维数组") || text.includes("二维数组")) {
      return "c_array";
    }
    if (text.includes("指针") || text.includes("地址") || text.includes("*p") || text.includes("取地址")) {
      return "c_pointer";
    }
    if (text.includes("函数") || text.includes("调用") || text.includes("return") || text.includes("参数")) {
      return "c_function";
    }
    if (text.includes("scanf") || text.includes("printf") || text.includes("输入") || text.includes("输出")) {
      return "c_io";
    }
    return "generic_programming";
  }
  if (text.includes("版本") || text.includes("python 2") || text.includes("python2") || text.includes("python 3") || text.includes("python3")) {
    return "python_version";
  }
  if (
    text.includes("伪代码")
    || text.includes("算法表示")
    || text.includes("算法描述")
    || text.includes("流程图")
    || text.includes("顺序结构")
    || text.includes("选择结构")
    || text.includes("循环结构")
  ) {
    return "python_pseudocode";
  }
  if (text.includes("if") || text.includes("else") || text.includes("elif") || text.includes("分支") || text.includes("条件") || text.includes("选择结构")) {
    return "python_branch";
  }
  if (text.includes("for") || text.includes("while") || text.includes("range") || text.includes("循环") || text.includes("遍历")) {
    return "python_loop";
  }
  if (text.includes("列表") || text.includes("字典") || text.includes("元组") || text.includes("字符串") || text.includes("索引") || text.includes("切片")) {
    return "python_sequence";
  }
  if (text.includes("文件") || text.includes("open") || text.includes("读写") || text.includes("读取") || text.includes("写入")) {
    return "python_file";
  }
  if (
    text.includes("变量")
    || text.includes("变量名")
    || text.includes("标识符")
    || text.includes("赋值")
    || text.includes("input")
    || text.includes("输入")
    || text.includes("输出")
    || text.includes("交换")
  ) {
    return "python_variable";
  }
  if (text.includes("函数") || text.includes("def") || text.includes("return") || text.includes("参数") || text.includes("调用")) {
    return "python_function";
  }
  if (text.includes("应用") || text.includes("领域") || text.includes("自动化") || text.includes("数据分析") || text.includes("人工智能")) {
    return "python_application";
  }
  if (text.includes("特点") || text.includes("特性") || text.includes("初识")) {
    return "python_feature";
  }
  return "generic_programming";
}

function isHighQualityQuizSet(items: AssessmentQuizItem[], courseName: string, topic: string): boolean {
  const firstThree = items.slice(0, 3);
  if (firstThree.length < 3 || firstThree.some((item) => item.options.length < 3)) {
    return false;
  }
  if (firstThree.some(isGenericQuizItem)) {
    return false;
  }
  if (courseLanguage(courseName, topic) === "Python" && firstThree.some((item) => hasCOnlyTerms(itemText(item)))) {
    return false;
  }
  if (fallbackTemplateKey(courseName, topic) === "python_variable") {
    return firstThree.some((item) => /变量名|标识符|input\(\)|int\(|赋值|交换|类型转换|2nd_value/.test(itemText(item)));
  }
  return hasProfessionalCoverage(fallbackTemplateKey(courseName, topic), firstThree.map(itemText).join("\n"));
}

function isHighQualityCodeChallenge(challenge: CodeAssessmentChallenge, courseName: string, topic: string): boolean {
  const text = `${challenge.prompt}\n${challenge.starterCode}\n${challenge.expectedOutput}`;
  if (hasGenericAssessmentText(text)) {
    return false;
  }
  if (courseLanguage(courseName, topic) === "Python" && hasCOnlyTerms(text)) {
    return false;
  }
  if (fallbackTemplateKey(courseName, topic) === "python_variable") {
    return /input\(\)|num1|num2|变量交换|交换前|交换后|int\(|读取|输入|变量|name|Hello|赋值|输出/.test(text);
  }
  return hasProfessionalCoverage(fallbackTemplateKey(courseName, topic), text);
}

function isGenericQuizItem(item: AssessmentQuizItem): boolean {
  return hasGenericAssessmentText(itemText(item));
}

function itemText(item: AssessmentQuizItem): string {
  return [item.prompt, ...item.options, item.dimension].join("\n");
}

function hasGenericAssessmentText(text: string): boolean {
  return [
    "核心作用",
    "只知道它出现在本节课中",
    "只知道它对应教材中的某一页",
    "只知道",
    "练习结果不符合预期",
    "跳过该知识点",
    "照抄示例",
    "是否看过视频",
    "是否记住"
  ].some((pattern) => text.includes(pattern));
}

function hasCOnlyTerms(text: string): boolean {
  return /#include\s*<stdio\.h>|int\s+main\s*\(|printf\s*\(|scanf\s*\(/.test(text);
}

function hasProfessionalCoverage(templateKey: AssessmentTemplateKey, text: string): boolean {
  const patterns: Record<AssessmentTemplateKey, RegExp> = {
    python_version: /Python 2|Python 3|版本|print|解释器/,
    python_application: /应用|领域|自动化|数据分析|库|pandas|Web|人工智能/,
    python_feature: /Python|语法|解释执行|库|特性|特点/,
    python_variable: /变量名|标识符|input\(\)|int\(|赋值|交换|类型转换|2nd_value/,
    python_pseudocode: /伪代码|算法|顺序|选择|循环|流程|累加/,
    python_branch: /if|else|elif|条件|分支|IndentationError/,
    python_loop: /for|while|range|循环|遍历|累加/,
    python_function: /def|函数|参数|return|调用/,
    python_sequence: /列表|字典|元组|字符串|索引|遍历|IndexError/,
    python_file: /open|文件|读取|写入|encoding|with/,
    c_io: /scanf|printf|格式控制符|输入|输出|&/,
    c_array: /数组|下标|a\[[^\]]+\]|越界|for/,
    c_pointer: /指针|地址|&x|\*p|解引用|野指针/,
    c_function: /函数|参数|return|返回类型|调用/,
    generic_programming: /输入|输出|语法|方法|错误/
  };
  return patterns[templateKey].test(text);
}

function questionId(rawNumber: string, index: number): string {
  const numeric = rawNumber.trim() || String(index + 1);
  return `agent_question_${numeric}`;
}

function cleanAssessmentText(text: string): string {
  return text
    .replace(/^\s*[-*]\s+/, "")
    .replace(/\s+/g, " ")
    .trim();
}

function answerIndex(answerLabel: string | undefined, options: string[]): number {
  if (!answerLabel) {
    return 0;
  }
  const label = answerLabel.trim();
  if (/^[A-Da-d]$/.test(label)) {
    return Math.min(options.length - 1, label.toUpperCase().charCodeAt(0) - 65);
  }
  const matchedIndex = options.findIndex((option) => option.includes(label) || label.includes(option));
  return matchedIndex >= 0 ? matchedIndex : 0;
}

function dimensionForIndex(index: number): string {
  return ["概念理解", "迁移应用", "调试反思"][index] || "综合应用";
}

function weightForIndex(index: number): number {
  return [0.35, 0.3, 0.35][index] || 0.25;
}

function normalizeWeights(items: AssessmentQuizItem[]): AssessmentQuizItem[] {
  const firstThree = items.slice(0, 3);
  if (!firstThree.length) {
    return [];
  }
  const total = firstThree.reduce((sum, item) => sum + item.weight, 0);
  if (total <= 0) {
    return firstThree.map((item, index) => ({ ...item, weight: weightForIndex(index) }));
  }
  return firstThree.map((item) => ({ ...item, weight: item.weight / total }));
}

function stripQuotes(text: string): string {
  return text.replace(/^["'“”‘’]+|["'“”‘’]+$/g, "").trim();
}

function inferExpectedOutput(prompt: string): string {
  const quoted = prompt.match(/[“"]([^”"]+)[”"]/);
  if (quoted?.[1]) {
    return quoted[1].trim();
  }
  return "PASS";
}

function normalizeOutput(output: string): string {
  return output.replace(/\r\n/g, "\n").trim();
}
