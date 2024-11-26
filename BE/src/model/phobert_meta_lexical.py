# Customize model PhoBert + Lexical
import torch.nn as nn
import torch.nn.functional as F
from transformers import XLMRobertaConfig
from transformers.modeling_outputs import SequenceClassifierOutput
from transformers.models.roberta.modeling_roberta import RobertaModel
from transformers.models.roberta.modeling_roberta import RobertaPreTrainedModel
from transformers.models.auto import AutoModelForPreTraining
import torch
from transformers import AutoTokenizer, AutoConfig

from utils import get_config


config = get_config()
model_base_phobert_lexical = config['model_checkpoint']['phobert_lexical_notld']
model_base_metadata = config['model_checkpoint']['phobert_meta_cls']
weight_pholexicalmeta = config['model_weight']['phobert_meta_lexical']


class PhoBertLexical(RobertaPreTrainedModel):
    def __init__(self, config):

        super().__init__(config)

        self.config = config
        self.config.id2label = {
            0: "Bình thường",
            1: "Tính nhiệm thấp",
        }
        self.config.label2id = {
            "Bình thường": 0,
            "Tính nhiệm thấp": 1,
        }

        self.roberta = RobertaModel(config, add_pooling_layer=False)
        self.fc1 = nn.Linear(10, 256)
        self.fc2 = nn.Linear(256, 768)
        self.dropout_nn = nn.Dropout(0.1)
        self.dropout_lm = nn.Dropout(0.1)

        # init weight
        self.init_weights()

    def forward(self, features, input_ids, attention_mask, token_type_ids):
        # output lexical
        x_nn = F.relu(self.fc1(features))
        x_nn = F.relu(self.fc2(x_nn))

        # output llm
        x_roberta = self.roberta(
            input_ids=input_ids,
            attention_mask=attention_mask,
            token_type_ids=token_type_ids).last_hidden_state[:, 0, :]

        x_nn = self.dropout_nn(x_nn)
        x_roberta = self.dropout_lm(x_roberta)

        return torch.cat((x_nn, x_roberta), dim=1)


class PhobertMeta(RobertaPreTrainedModel):
    def __init__(self, config):
        super().__init__(config)
        self.roberta = RobertaModel(config, add_pooling_layer=False)
        self.dropout_llm = nn.Dropout(0.1)
        # init weight
        self.init_weights()

    def forward(self, input_ids_meta, attention_mask_meta, token_type_ids_meta):

        x_meta_emb = self.roberta(
            input_ids=input_ids_meta,
            attention_mask=attention_mask_meta,
            token_type_ids=token_type_ids_meta).last_hidden_state[:, 0, :]

        x_meta_emb = self.dropout_llm(x_meta_emb)

        return x_meta_emb  # hàm trainer cần cái này nó mới chịu train


class PhobertLexicalMeta(nn.Module):
    def __init__(self, config):
        super(PhobertLexicalMeta, self).__init__()

        self.config = config
        self.config.num_classes = 2
        self.phobertlexical = PhoBertLexical.from_pretrained(
            model_base_phobert_lexical,
            config=self.config
        )
        self.phobertMeta = PhobertMeta.from_pretrained(
            model_base_metadata,
            config=self.config
        )

        self.out = nn.Linear(2304, 2)

    def forward(
            self,
            features,
            input_ids,
            attention_mask,
            token_type_ids,
            input_ids_meta,
            attention_mask_meta,
            token_type_ids_meta,
            labels=None,

    ):
        x_lexical_emb = self.phobertlexical(
            features,
            input_ids=input_ids,
            attention_mask=attention_mask,
            token_type_ids=token_type_ids
        )

        x_meta_emb = self.phobertMeta(
            input_ids_meta=input_ids_meta,
            attention_mask_meta=attention_mask_meta,
            token_type_ids_meta=token_type_ids_meta
        )

        logits = self.out(torch.cat((x_lexical_emb, x_meta_emb), dim=1))

        loss = None
        if labels is not None:
            if labels.dtype != torch.long:
                labels = labels.long()
            loss_fct = nn.CrossEntropyLoss()
            loss = loss_fct(
                logits.view(-1, self.config.num_classes), labels.view(-1))

        return SequenceClassifierOutput(loss=loss, logits=logits)


device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
phobert_config = AutoConfig.from_pretrained(model_base_metadata)
phobert_lexical_meta_tokenizer = AutoTokenizer.from_pretrained(
    model_base_metadata)

model_phobert_lexical_meta = PhobertLexicalMeta(
    config=phobert_config)


model_phobert_lexical_meta.load_state_dict(
    torch.load(weight_pholexicalmeta, map_location=torch.device(device))
)